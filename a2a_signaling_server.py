"""
Compatibility shim for legacy Railway startCommand.

Some historical deployments start with `uvicorn a2a_signaling_server:app`.
To guarantee production always serves the latest signaling hub,
this module re-exports `cloud_server.signaling_hub:app`.
"""

from cloud_server.signaling_hub import app


if __name__ == "__main__":
    import os
    import uvicorn

    uvicorn.run(
        "cloud_server.signaling_hub:app",
        host="0.0.0.0",
        port=int(os.getenv("PORT", "8080")),
        workers=1,
        log_level="info",
    )
