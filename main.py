from os import listdir
from os.path import isfile, join
from typing import List, Union

from fastapi.responses import HTMLResponse, RedirectResponse, JSONResponse, FileResponse
from pathlib import Path
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi import Request, Response
from fastapi import Header
from fastapi.templating import Jinja2Templates

CHUNK_SIZE = 1024*1024



app = FastAPI()
templates = Jinja2Templates(directory="templates")
video_path = Path("temp/video.mp4")
rooms = {}
favicon_path = 'favicon.ico'


class ConnectionManager:
    def __init__(self):
        self.active_connections: List[WebSocket] = []

    async def connect(self, websocket: WebSocket, room_id: str):
        await websocket.accept()
        self.active_connections.append(websocket)
        rooms[room_id]['users'].append(websocket)

    def disconnect(self, websocket: WebSocket, room_id: str):
        self.active_connections.remove(websocket)
        rooms[room_id]['users'].remove(websocket)

    async def broadcast(self, websocket, message: str, room_id: str):
        for connection in rooms[room_id]['users']:
            if connection != websocket:
                await connection.send_text(message)


manager = ConnectionManager()


@app.get("/")
async def read_root(request: Request):
    return templates.TemplateResponse("index.htm", context={"request": request})

@app.get('/favicon.ico', include_in_schema=False)
async def favicon():
    return FileResponse(favicon_path)


@app.get("/video/{id}")
async def video_endpoint(id, range: str = Header(None)):
    print('video endpoint')
    video_path = Path("temp/" + id)
    if range:
        start, end = range.replace("bytes=", "").split("-")
        start = int(start)
        end = int(end) if end else start + CHUNK_SIZE
        print('video endpoint end 1')
    else:
        start = 0
        end = start + CHUNK_SIZE
        print('video endpoint end 2')
    with open(video_path, "rb") as video:
        filesize = str(video_path.stat().st_size)
        video.seek(start)
        print('video endpoint end 3')
        data = video.read(end - start)
        if end - start > len(data):
            end = int(filesize)-1
        headers = {
            'Content-Range': f'bytes {str(start)}-{str(end)}/{filesize}',
            'Accept-Ranges': 'bytes'
        }
        print('video endpoint end')
        return Response(data, status_code=206, headers=headers, media_type="video/mp4")


@app.post("/enter_room/{id}")
async def enter_room(id:str):
    if id not in rooms.keys():
        rooms[id] = {}
        rooms[id]['users'] = []
    response = RedirectResponse(url=f'/room/{id}')
    return response


@app.post("/room/{id}", response_class=HTMLResponse)
async def join_room(request: Request,id:str):
    if 'film' in rooms[id].keys():
        return templates.TemplateResponse("video_playback.htm", context={"request": request, "link": rooms[id]['film']})
    return templates.TemplateResponse("room.htm", context={"request": request, "id": id})   #TODO return list of videos on server

@app.get("/room/{id}/{film_id}", response_class=HTMLResponse)
async def join_room(request: Request,id:str, film_id, url: Union[str, None] = None):
    if url:
        url = url.replace('watch', 'embed')
        film_id = url
    else:
        film_id = '/video/' + film_id
    if id not in rooms.keys():
        rooms[id] = {}
        rooms[id]['users'] = []
    rooms[id]['film'] = film_id
    rooms[id]['state'] = 'stopped'
    return templates.TemplateResponse("video_playback.htm", context={"request": request, "link": rooms[id]['film']})   #TODO return list of videos on server


@app.get("/films")
async def get_all_films():
    films_list = {}
    films_list['films'] = [f for f in listdir('temp') if isfile(join('temp', f))]
    return JSONResponse(content=films_list)                                                             

@app.websocket("/room/{id}/controls")
async def control_playback(websocket: WebSocket, id:str):
    await manager.connect(websocket, id)
    try:
        while True:
            data = await websocket.receive_text()
            await manager.broadcast(websocket, data, id)
    except WebSocketDisconnect:
        manager.disconnect(websocket, id)
        