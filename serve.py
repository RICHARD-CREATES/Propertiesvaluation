"""
Runner script for launching the Global AI Property Valuation Server.
"""
import os
import uvicorn

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8000))
    print("=" * 75)
    print("  LAUNCHING GLOBAL AI PROPERTY VALUATION PLATFORM")
    print(f"  Open your browser at: http://localhost:{port}")
    print("=" * 75)
    uvicorn.run("src.api.app:app", host="0.0.0.0", port=port, reload=False)
