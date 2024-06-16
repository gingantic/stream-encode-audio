import aiohttp
import asyncio
import subprocess
import pyaudio
import threading

download_data = b''
encode_data = b''

file_size = 0
download_done = False
encode_done = False

async def download_file(url):
    global download_data, file_size, download_done

    print(f"Downloading {url}")
    async with aiohttp.ClientSession() as session:
        async with session.get(url) as response:
            file_size = int(response.headers.get('Content-Length', 0))
            print(f"File size: {file_size} bytes")
            current_size = 0
            if response.status == 200:
                print("Download started")
                while True:
                    chunk = await response.content.read(1024*16)
                    if not chunk:
                        break
                    print(f"Downloaded {len(chunk)} bytes | {current_size}/{file_size} bytes | {current_size/file_size*100:.2f}%")
                    current_size += len(chunk)
                    download_data += chunk
            else:
                print(f"Failed to download file. HTTP status code: {response.status}")
    download_done = True

async def encode_file(ffmpeg_command):
    global encode_done

    current_chunk = 0
    buf_chunk = 1024*32

    print("Encoding file")

    process = await asyncio.create_subprocess_exec(
        *ffmpeg_command,
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE
    )

    async def read_stream():
        global encode_data
        while True:
            chunk = await process.stdout.read(1024*32)
            if not chunk:
                break
            encode_data += chunk
    
    loop = asyncio.get_event_loop()
    read_task = loop.create_task(read_stream())

    while True:
        
        if download_done and current_chunk >= len(download_data):
            print("All data read")
            break

        if len(download_data) - current_chunk < buf_chunk:
            if not download_done:
                print("Waiting for more data")
                await asyncio.sleep(1)
                continue

        chunk = download_data[current_chunk:current_chunk+buf_chunk]

        process.stdin.write(chunk)
        await process.stdin.drain()

        current_chunk += buf_chunk

    process.stdin.close()
    await process.wait()

    if process.returncode != 0:
        print(f"ffmpeg failed with return code {process.returncode}")

    await read_task

    encode_done = True

def play_audio():

    current_chunk = 0
    buf_chunk = 1024

    p = pyaudio.PyAudio()
    stream = p.open(format=pyaudio.paInt16,
                    channels=2,
                    rate=48000,
                    output=True)

    while True:
        if encode_done and current_chunk >= len(encode_data):
            print("All data played")
            break

        if len(encode_data) - current_chunk < buf_chunk:
            if not encode_done:
                continue
        
        chunk = encode_data[current_chunk:current_chunk+buf_chunk]

        stream.write(chunk)

        current_chunk += buf_chunk
    
    stream.stop_stream()
    stream.close()
    p.terminate()

async def main():
    url = '<URL_TO_AUDIO_FILE>'

    ffmpeg_command = [
        'ffmpeg',
        '-i', 'pipe:0',
        '-ar', '48000',
        '-ac', '2',
        '-vn', 
        '-f', 'wav',
        '-'
    ]

    downloader = asyncio.create_task(download_file(url))
    encoder = asyncio.create_task(encode_file(ffmpeg_command))

    audio_thread = threading.Thread(target=play_audio)
    audio_thread.start()

    await downloader
    await encoder

    audio_thread.join()

if __name__ == '__main__':
    asyncio.run(main())
