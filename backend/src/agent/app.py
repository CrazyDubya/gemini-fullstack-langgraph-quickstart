# mypy: disable - error - code = "no-untyped-def,misc"
import pathlib
from fastapi import FastAPI, Request, Response, File, UploadFile, HTTPException
from fastapi.staticfiles import StaticFiles
import fastapi.exceptions
import os
import shutil # For saving file

# Define the FastAPI app
app = FastAPI()


def create_frontend_router(build_dir="../frontend/dist"):
    """Creates a router to serve the React frontend.

    Args:
        build_dir: Path to the React build directory relative to this file.

    Returns:
        A Starlette application serving the frontend.
    """
    build_path = pathlib.Path(__file__).parent.parent.parent / build_dir
    static_files_path = build_path / "assets"  # Vite uses 'assets' subdir

    if not build_path.is_dir() or not (build_path / "index.html").is_file():
        print(
            f"WARN: Frontend build directory not found or incomplete at {build_path}. Serving frontend will likely fail."
        )
        # Return a dummy router if build isn't ready
        from starlette.routing import Route

        async def dummy_frontend(request):
            return Response(
                "Frontend not built. Run 'npm run build' in the frontend directory.",
                media_type="text/plain",
                status_code=503,
            )

        return Route("/{path:path}", endpoint=dummy_frontend)

    build_dir = pathlib.Path(build_dir)

    react = FastAPI(openapi_url="")
    react.mount(
        "/assets", StaticFiles(directory=static_files_path), name="static_assets"
    )

    @react.get("/{path:path}")
    async def handle_catch_all(request: Request, path: str):
        fp = build_path / path
        if not fp.exists() or not fp.is_file():
            fp = build_path / "index.html"
        return fastapi.responses.FileResponse(fp)

    return react


# Mount the frontend under /app to not conflict with the LangGraph API routes
app.mount(
    "/app",
    create_frontend_router(),
    name="frontend",
)

# Directory to store uploaded PDFs temporarily
PDF_UPLOAD_DIR = "temp_pdfs"
os.makedirs(PDF_UPLOAD_DIR, exist_ok=True)

@app.post("/upload_pdf/")
async def upload_pdf(file: UploadFile = File(...)):
    """
    Endpoint to upload a PDF file.
    Saves the file to a temporary directory and returns its name and path.
    """
    if not file.filename:
        raise HTTPException(status_code=400, detail="No filename provided.")

    if file.content_type != "application/pdf":
        raise HTTPException(status_code=400, detail="Invalid file type. Only PDFs are allowed.")

    try:
        # Ensure the filename is secure and create a valid path
        # For simplicity, using the original filename. In production, generate a unique, secure name.
        file_path = os.path.join(PDF_UPLOAD_DIR, file.filename)

        # Save the file
        with open(file_path, "wb") as buffer:
            shutil.copyfileobj(file.file, buffer)

        # The path returned should be accessible by the agent.
        # If running in Docker, this path is relative to the container's root or working directory.
        # Assuming /app is the working directory in the Docker container, as is common.
        # If PDF_UPLOAD_DIR is relative like "temp_pdfs", then it's /app/temp_pdfs.
        # If it's absolute like "/tmp/temp_pdfs", then it's that.
        # For now, let's assume the agent can access it via this relative path from /app.
        # The agent's working directory is /app in the Dockerfile.
        accessible_path = file_path # This will be relative to /app, e.g., "temp_pdfs/filename.pdf"

        return {"name": file.filename, "path": accessible_path}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Could not save file: {e}")
    finally:
        if hasattr(file, 'file') and not file.file.closed:
            file.file.close()
