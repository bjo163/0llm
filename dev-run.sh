source .venv/bin/activate
pip install -r requirements.txt 
pip install -U g4f[all]

#python -m g4f.cli gui --port 8080 --debug
#python -m g4f --debug --port 8080

#python -m g4f.cli gui --port 8080 --debug
#python -m g4f.cli api --port 1337 --debug

#python -m g4f.api.run
#python -m g4f.gui.run
python -m g4f --port 8080 --debug ## RUN ALL