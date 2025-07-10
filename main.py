from fastapi import FastAPI, Request, Form, WebSocket, WebSocketDisconnect
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from starlette.middleware.sessions import SessionMiddleware
import uuid, json

app = FastAPI()
app.add_middleware(SessionMiddleware, secret_key="super-secret")

app.mount("/static", StaticFiles(directory="static"), name="static")
templates = Jinja2Templates(directory="templates")

# Sessões e estado
users = {}  # nickname -> senha
connections: dict[str, list[tuple[WebSocket, str]]] = {}
game_states: dict[str, dict] = {}

def inicializar_estado_partida(partida_id: str):
    game_states[partida_id] = {
        "turno": 0,
        "jogador_da_vez": None,
        "vida": {},
        "pontuacao": {},
    }

@app.get("/", response_class=HTMLResponse)
def login_page(request: Request):
    return templates.TemplateResponse("login.html", {"request": request})

@app.post("/login")
def login(request: Request, nickname: str = Form(...), senha: str = Form(...)):
    if nickname not in users:
        users[nickname] = senha
    elif users[nickname] != senha:
        return RedirectResponse("/", status_code=302)

    request.session["user"] = nickname
    return RedirectResponse("/dashboard", status_code=302)

@app.get("/dashboard", response_class=HTMLResponse)
def dashboard(request: Request):
    user = request.session.get("user")
    if not user:
        return RedirectResponse("/", status_code=302)
    return templates.TemplateResponse("dashboard.html", {"request": request, "user": user})

@app.get("/criar_partida")
def criar_partida(request: Request):
    partida_id = str(uuid.uuid4())[:8]
    return RedirectResponse(f"/partida/{partida_id}", status_code=302)

@app.get("/partida/{partida_id}", response_class=HTMLResponse)
def partida_page(request: Request, partida_id: str):
    user = request.session.get("user")
    if not user:
        return RedirectResponse("/", status_code=302)
    return templates.TemplateResponse("partida.html", {
        "request": request,
        "partida_id": partida_id,
        "user": user
    })

@app.get("/espectador/{partida_id}", response_class=HTMLResponse)
def espectador_page(request: Request, partida_id: str):
    user = request.session.get("user")
    if not user:
        return RedirectResponse("/", status_code=302)
    return templates.TemplateResponse("espectador.html", {
        "request": request,
        "partida_id": partida_id,
        "user": user
    })

# === WebSocket ===

@app.websocket("/ws/{partida_id}")
async def websocket_endpoint(websocket: WebSocket, partida_id: str):
    await websocket.accept()
    nickname = ""

    try:
        while True:
            data = await websocket.receive_text()
            msg = json.loads(data)

            if msg["type"] == "join":
                nickname = msg["nickname"]
                if partida_id not in connections:
                    connections[partida_id] = []
                    inicializar_estado_partida(partida_id)

                connections[partida_id].append((websocket, nickname))

                # Inicializa vida e pontos
                if nickname not in game_states[partida_id]["vida"]:
                    game_states[partida_id]["vida"][nickname] = 20
                    game_states[partida_id]["pontuacao"][nickname] = 0

                # Primeiro jogador da vez
                if game_states[partida_id]["jogador_da_vez"] is None:
                    game_states[partida_id]["jogador_da_vez"] = nickname

                await broadcast_participants(partida_id)
                await broadcast_estado(partida_id)

            elif msg["type"] == "passar-turno":
                estado = game_states[partida_id]
                estado["turno"] += 1

                jogadores = list(estado["vida"].keys())
                atual = jogadores.index(estado["jogador_da_vez"])
                proximo = (atual + 1) % len(jogadores)
                estado["jogador_da_vez"] = jogadores[proximo]

                await broadcast_estado(partida_id)

            elif msg["type"] == "signal":
                for conn, _ in connections.get(partida_id, []):
                    if conn != websocket:
                        await conn.send_text(data)

            elif msg["type"] == "ice-candidate":
                for conn, _ in connections.get(partida_id, []):
                    if conn != websocket:
                        await conn.send_text(data)

    except WebSocketDisconnect:
        if partida_id in connections:
            connections[partida_id] = [
                (ws, name) for ws, name in connections[partida_id] if ws != websocket
            ]
        await broadcast_participants(partida_id)
        await broadcast_estado(partida_id)

async def broadcast_participants(partida_id: str):
    names = [name for _, name in connections.get(partida_id, [])]
    for conn, _ in connections.get(partida_id, []):
        await conn.send_text(json.dumps({
            "type": "participants",
            "users": names
        }))

async def broadcast_estado(partida_id: str):
    estado = game_states[partida_id]
    for conn, _ in connections.get(partida_id, []):
        await conn.send_text(json.dumps({
            "type": "estado",
            "estado": estado
        }))
