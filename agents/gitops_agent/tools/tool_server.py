from fastapi import FastAPI
from pydantic import BaseModel
from handlers.clone_repo import run_clone_repo
from handlers.license_audit import run_license_audit
from handlers.config_validator import run_config_validation
from handlers.repo_size import run_repo_size
from fastapi.responses import JSONResponse
import uvicorn
import traceback2 as traceback

app = FastAPI(title="DevOps Tool Server", version="1.0")

# Tool function registry
TOOL_REGISTRY = {
    "clone_repo": run_clone_repo,
    "license_audit": run_license_audit,
    "config_validator": run_config_validation,
    "repo_size": run_repo_size,
}

# Request body schema
class ToolInvokeRequest(BaseModel):
    tool_name: str
    input: dict

class ToolInvokeResponse(BaseModel):
    status: str
    output: dict

# POST endpoint for tool invocation
@app.post("/invoke", response_model=ToolInvokeResponse)
def invoke_tool(req: ToolInvokeRequest):
    if req.tool_name not in TOOL_REGISTRY:
        return {"status": "error", "output": {"message": f"Unknown tool: {req.tool_name}"}}

    try:
        result = TOOL_REGISTRY[req.tool_name](req.input)
        return {"status": "success", "output": result}
    except Exception as e:
        tb = traceback.format_exc()
        print("Exception Traceback:\n", tb)
        return {"status": "error", "output": {"message": str(e)}}

# GET endpoint for health check
@app.get("/health")
def health():
    return JSONResponse(content={"status": "ok"}, status_code=200)

# Run the server
if __name__ == "__main__":
    uvicorn.run(app, host="127.0.0.1", port=8001)