from fastapi import FastAPI, Request, Form, Depends
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from starlette.middleware.sessions import SessionMiddleware
from uuid import uuid4
from fastapi.responses import JSONResponse
from fastapi import WebSocket, WebSocketDisconnect


app = FastAPI()

# Middleware de sessão
app.add_middleware(SessionMiddleware, secret_key="supersecretkey")

# Templates e arquivos estáticos
app.mount("/static", StaticFiles(directory="static"), name="static")
templates = Jinja2Templates(directory="templates")

# Simulação de banco de dados de usuários
fake_users = {
    "player1": "senha123",
    "player2": "abc123",
}

@app.get("/", response_class=HTMLResponse)
def login_page(request: Request):
    return templates.TemplateResponse("login.html", {"request": request, "error": None})

@app.post("/login")
def login(request: Request, nickname: str = Form(...), senha: str = Form(...)):
    if nickname in fake_users and fake_users[nickname] == senha:
        request.session["user"] = nickname
        return RedirectResponse("/dashboard", status_code=302)
    else:
        return templates.TemplateResponse("login.html", {"request": request, "error": "Nickname ou senha inválidos"})

@app.get("/dashboard", response_class=HTMLResponse)
def dashboard(request: Request):
    user = request.session.get("user")
    if not user:
        return RedirectResponse("/", status_code=302)
    return templates.TemplateResponse("dashboard.html", {"request": request, "user": user})

# Criar nova partida
@app.get("/criar", response_class=HTMLResponse)
def criar_partida(request: Request):
    user = request.session.get("user")
    if not user:
        return RedirectResponse("/", status_code=302)
    
    # Gera ID único da partida
    partida_id = str(uuid4())
    return RedirectResponse(f"/partida/{partida_id}", status_code=302)

# Página da partida
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

# Página do celular (modo câmera)
@app.get("/camera/{partida_id}", response_class=HTMLResponse)
def camera_page(request: Request, partida_id: str):
    return templates.TemplateResponse("camera.html", {
        "request": request,
        "partida_id": partida_id
    })

#Página modo espectador
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


# Mapeamento de conexões por partida
connections: dict[str, list[WebSocket]] = {}

@app.websocket("/ws/{partida_id}")
async def websocket_endpoint(websocket: WebSocket, partida_id: str):
    await websocket.accept()

    if partida_id not in connections:
        connections[partida_id] = []

    connections[partida_id].append(websocket)

    try:
        while True:
            data = await websocket.receive_text()
            # Encaminha para todos os outros usuários da partida
            for conn in connections[partida_id]:
                if conn != websocket:
                    await conn.send_text(data)
    except WebSocketDisconnect:
        connections[partida_id].remove(websocket)
