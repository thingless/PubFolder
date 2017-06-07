# PubFolder

PubFolder emulates Dropbox's discontinued public folder.

## Why build PubFolder?

We missed Dropbox's public folders. We liked the ability to predict a files path and the ability to directly link to a file (without viewing it in Dropbox's UI).

## Do I have to host the project myself?

No, we have a hosted version at [pubfolder.com](https://pubfolder.com/).

## Running the code

1. Create a virtualenv `virtualenv -p python3 venv`
2. Install the requirements `pip install -r requirements.txt`
3. Install and run redis
3. Run the web server with `COOKIE_SECRET=SOME_RND_STRING BASE_URL=http://localhost:8000/ DBX_APP_KEY=6666666666 DBX_APP_SECRET=7777777777 python server.py` replacing environment variable values. You can get the Dropbox app key & secret by createing a [new Dropbox App](https://www.dropbox.com/developers/apps).