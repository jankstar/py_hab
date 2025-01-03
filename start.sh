source env/bin/activate
export HF_HOME=./build 
export MKL_THREADING_LAYER=TBB
uvicorn main:app --workers 2 --host 0.0.0.0 --port 8000

