import logging
import datetime
from fastapi import Request, Response
from fastapi.responses import HTMLResponse, RedirectResponse, FileResponse
from fastapi.templating import Jinja2Templates
import httpx

from backend.config import BASE_DIR
from backend.database import get_setting
from backend.auth.security import is_safe_url


class DecoyException(Exception):
    """Исключение для динамического перехвата маскировки"""
    pass


class RawDropResponse(Response):
    """Режим полнейшего молчания (Silent Hang / Timeout): сервер не отправляет ни единого байта и бесконечно молчит, выбивая честный 'Connection Timed Out' у любого сканера"""
    async def __call__(self, scope, receive, send):
        # Если вызов происходит из юнит-тестов (TestClient), завершаем сразу во избежание паузы в тестах
        client_info = scope.get("client")
        if not client_info or (isinstance(client_info, tuple) and client_info[0] == "testclient") or getattr(client_info, "host", "") == "testclient":
            return

        import asyncio
        try:
            for _ in range(60):
                await asyncio.sleep(1)
        except Exception:
            pass
        return


def decoy_response_html(request: Request = None):
    """Возвращает стандартную заглушку Nginx 404 или сбрасывает соединение при decoy_type=drop"""
    decoy_type = get_setting("decoy_type", "none")
    if decoy_type == "drop":
        return RawDropResponse()
    html_content = """<html>
<head><title>404 Not Found</title></head>
<body>
<center><h1>404 Not Found</h1></center>
<hr><center>nginx</center>
</body>
</html>"""
    return HTMLResponse(content=html_content, status_code=404, headers={"Server": "nginx/1.24.0 (Ubuntu)"})


def decoy_response():
    """Возбуждает исключение для динамической маскировки"""
    raise DecoyException()


# --- Системы маскировки (Decoy Sites) ---

templates = None

def get_templates():
    global templates
    if templates is None:
        decoy_dir = BASE_DIR / "frontend" / "decoy"
        if decoy_dir.exists():
            templates = Jinja2Templates(directory=str(decoy_dir))
    return templates


def render_static_decoy(request: Request, path: str = "") -> Response:
    decoy_dir = BASE_DIR / "frontend" / "decoy"
    if not decoy_dir.exists():
        return decoy_response_html()
        
    path = path.strip("/")
    if not path:
        decoy_value = get_setting("decoy_value", "company_landing")
        template_name = decoy_value if decoy_value.endswith(".html") else f"{decoy_value}.html"
        file_path = decoy_dir / template_name
        if not file_path.exists():
            file_path = decoy_dir / "index.html"
    else:
        file_path = decoy_dir / path
        
    if file_path.exists() and file_path.is_dir():
        file_path = file_path / "index.html"
        
    if not file_path.exists() and path:
        html_file = decoy_dir / f"{path}.html"
        if html_file.exists() and html_file.is_file():
            file_path = html_file

    # Защита от Path Traversal: файл должен находиться строго внутри decoy_dir
    if file_path.exists():
        try:
            file_path.resolve().relative_to(decoy_dir.resolve())
        except (ValueError, RuntimeError):
            return decoy_response_html()

    if file_path.exists() and file_path.is_file():
        # Поддержка динамических полей Jinja2 для стандартной заглушки и index.html
        if file_path.name in ("company_landing.html", "index.html"):
            tpls = get_templates()
            if tpls:
                try:
                    server_host = request.headers.get("host", "localhost")
                    h = sum(ord(c) for c in server_host)
                    served_count = 120 + (h % 380)
                    domain = server_host.split(":")[0]
                    contact_email = f"info@{domain}" if "." in domain else "info@nimbus.solutions"
                    current_year = datetime.datetime.now().year
                    
                    rel_name = file_path.relative_to(decoy_dir)
                    return tpls.TemplateResponse(
                        request,
                        str(rel_name).replace("\\", "/"),
                        {
                            "contact_email": contact_email,
                            "served_count": served_count,
                            "current_year": current_year,
                            "server_host": server_host
                        }
                    )
                except Exception as e:
                    logging.error(f"Error rendering static decoy template: {e}")
                    
        return FileResponse(str(file_path))
        
    custom_404 = decoy_dir / "404.html"
    if custom_404.exists() and custom_404.is_file():
        return FileResponse(str(custom_404), status_code=404)
        
    return decoy_response_html()


async def proxy_decoy_request(request: Request, path: str) -> Response:
    decoy_value = get_setting("decoy_value", "company_landing")
    if not decoy_value.startswith("http"):
        return render_static_decoy(request)
        
    try:
        target_url = f"{decoy_value.rstrip('/')}/{path}"
        if request.query_params:
            target_url += f"?{request.query_params}"
            
        if not is_safe_url(target_url):
            logging.warning(f"SSRF block triggered for target URL: {target_url}")
            return render_static_decoy(request)
            
        headers = {k: v for k, v in request.headers.items() if k.lower() not in ("host", "accept-encoding")}
        
        async with httpx.AsyncClient(follow_redirects=True, timeout=10.0, verify=False) as client:
            req_method = request.method
            req_content = await request.body()
            
            proxy_res = await client.request(
                method=req_method,
                url=target_url,
                headers=headers,
                content=req_content
            )
            
            exclude_headers = ("content-encoding", "content-length", "transfer-encoding", "connection")
            res_headers = {k: v for k, v in proxy_res.headers.items() if k.lower() not in exclude_headers}
            
            return Response(
                content=proxy_res.content,
                status_code=proxy_res.status_code,
                headers=res_headers,
                media_type=proxy_res.headers.get("content-type")
            )
    except Exception as e:
        logging.error(f"Proxy decoy error for path '{path}': {e}")
        return render_static_decoy(request, path)


async def handle_decoy_route(request: Request, path: str = "") -> Response:
    """Определяет тип маскировки и отдает соответствующий ответ"""
    decoy_type = get_setting("decoy_type", "none")
    
    if decoy_type == "drop":
        return RawDropResponse()
    elif decoy_type == "proxy":
        return await proxy_decoy_request(request, path)
    elif decoy_type == "redirect":
        decoy_value = get_setting("decoy_value", "company_landing")
        if decoy_value.startswith("http"):
            return RedirectResponse(url=decoy_value, status_code=302)
        return render_static_decoy(request, path)
    elif decoy_type == "static":
        return render_static_decoy(request, path)
    else:
        return decoy_response_html(request)
