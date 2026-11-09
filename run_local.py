"""Start the API using ignored .env settings, without extra dotenv dependencies."""
from local_env import load_local_env

if __name__ == '__main__':
    load_local_env()
    import uvicorn
    uvicorn.run('api:app', host='127.0.0.1', port=8000, reload=True)
