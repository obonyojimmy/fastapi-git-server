import os
import subprocess
import gzip
from fastapi import FastAPI, Request, Response, HTTPException, Depends
from fastapi.security import HTTPBasic, HTTPBasicCredentials
from fastapi.responses import StreamingResponse
from git import Repo, GitCommandError
from typing import Optional

# Configuration variables
PROJECTS_PATH = "/path/to/projects"
GIT_REPOS_PATH = "/path/to/git/repos"
GIT_PATH = "/usr/bin/git"
SERVER_HOST = "0.0.0.0"
SERVER_PORT = 8000
USER_NAME = "username"
PASSWORD = "password"

app = FastAPI()
security = HTTPBasic()

def verify_password(credentials: HTTPBasicCredentials = Depends(security)):
	correct_username = credentials.username == USER_NAME
	correct_password = credentials.password == PASSWORD
	if not (correct_username and correct_password):
		raise HTTPException(status_code=401, detail="Incorrect username or password")
	return True

def git_command_with_input(repo_name, version, data, *args):
	repo_path = os.path.join(GIT_REPOS_PATH, repo_name)
	cmd = [GIT_PATH, *args]
	gitdir = repo_path + '/.git'
	p = subprocess.Popen(' '.join(cmd), cwd=gitdir, shell=True, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
	p.stdin.write(data)
	p.stdin.flush()
	for line in p.stdout:
		yield line
		

def git_command(repo_name, version, *args):
	repo_path = os.path.join(GIT_REPOS_PATH, repo_name)
	cmd = [GIT_PATH, *args]
	gitdir = repo_path + '/.git'
	p = subprocess.Popen(' '.join(cmd), cwd=gitdir, shell=True, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
	p.wait()
	return p.stdout.read()

@app.post("/{repo_name}/git-upload-pack")
@app.post("/{repo_name}.git/git-upload-pack")
async def git_upload_pack(repo_name: str, request: Request):
	repo_name += '.git'
	data = await request.body()
	data = await request.body()
	if request.headers.get("Content-Encoding") == "gzip":
		data = gzip.decompress(data)
	args = ['upload-pack', "--stateless-rpc", '.']
	res = git_command_with_input(repo_name, '', data, *args)
	return StreamingResponse(content=res, media_type="application/x-git-upload-pack-result")

@app.post("/{repo_name}/git-receive-pack")
@app.post("/{repo_name}.git/git-receive-pack")
async def git_receive_pack(repo_name: str, request: Request, credentials: HTTPBasicCredentials = Depends(security)):
	verify_password(credentials)
	repo_name += '.git'
	data = await request.body()
	args = ['receive-pack', "--stateless-rpc", '.']
	res = git_command_with_input(repo_name, '', data, *args)
	return StreamingResponse(content=res, media_type="application/x-git-receive-pack-result")

@app.get("/{repo_name}/info/refs")
@app.get("/{repo_name}.git/info/refs")
async def git_info_refs(repo_name: str, request: Request, credentials: Optional[HTTPBasicCredentials] = Depends(security)):
	repo_name += '.git'
	service = request.query_params.get('service')
	service_name = service[4:] if service and 'git-' in service else 'upload-pack'
	
	if service_name == 'receive-pack':
		verify_password(credentials)

	args = [service_name, "--stateless-rpc", "--advertise-refs", "."]
	res = git_command(repo_name, '', *args)
	first_line = f'# service=git-{service_name}\n0000'
	first_line = f'{len(first_line):04x}{first_line}'

	headers = {"Content-Type": f"application/x-git-{service_name}-advertisement"}
	return Response(content=first_line.encode() + res, headers=headers)

if __name__ == "__main__":
	import uvicorn
	uvicorn.run(app, host=SERVER_HOST, port=SERVER_PORT)
