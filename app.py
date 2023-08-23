import audioop
import base64
import json
from flask import Flask, request
from flask_sock import Sock, ConnectionClosed
from twilio.twiml.voice_response import VoiceResponse, Start
from twilio.rest import Client
from urllib.parse import quote
import websocket
import base64
from threading import Thread
from pydub import AudioSegment
import io
from urllib.parse import urlencode
import requests
from context import prompt
from data import user_info


ASSEMBLYAI_API_KEY = ""
TWILIO_ACCOUNT_SID = ""
TWILIO_AUTH_TOKEN = ""

NGROK_URL = ""

app = Flask(__name__)
sock = Sock(app)
twilio_client = Client(TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN)

CL = '\x1b[0K'
BS = '\x08'



# Twilio Text to Speech on Call
def speak(text):
    # Connect to the Twilio API
    client = Client(TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN)
    # Encode the text to be spoken
    encoded_text = quote(text)
    # Update the ongoing call with the new TwiML URL
    try:
        # Check to see if we are currently answering a question
        global answering_question
        if answering_question:
            # Update the call with the new TwiML URL + text to be spoken
            call = client.calls(call_sid).update(url=NGROK_URL +"/response?text="+encoded_text, method='POST')
            print(f'Call updated with text: {text}')
            
        else:
            print(f'Not updating call with text: {text}')
    except Exception as e:
        print(f'Error updating call: {e}')
    
# AssemblyAI Question Answering via LeMUR
def ask(question):
    global questions
    if question not in questions:
        #NOTICE - this url represents a server that is not publicly available. Please replace with a proper LeMUR api call
        #NOTICE - LeMUR as of August 22, 2023 requires a transcript ID parameter.  
        #LeMUR will become fully multi modal soon, but for now, please pass in a stand-in transcript of < 10 seconds long as a placeholder. 
        #Contact AAI solutions for more information
        url = "https://assemblyai-solutions-example.com" 
        global conversation_history
        # Send the question to LeMUR
        # Provide user_info and prompt as context
        # This example uses LeMUR's QA endpoint. the question history and question context are merged for live API calls
        payload = json.dumps({
        "question": question,
        "conversation_history": conversation_history,
        "context": {"data": user_info, "context": prompt}
        })
        headers = {
        'Content-Type': 'application/json',
        'Authorization': ASSEMBLYAI_API_KEY
        }
        response = requests.request("POST", url, headers=headers, data=payload)
        answer = response.text
        # Store conversation hisotry
        conversation_history.append({"question": question, "answer": answer})
        # Add the question to the list of questions
        questions.append(question)
        return answer
    else:
        return None

# AssemblyAI WebSocket Response Handler
def handle_assembly_messages(assembly_ws):
    # AssemblyAI returns a JSON message with a message_type property
    # The message_type property can be one of the following:
    # SessionBegins - This message is sent when the WebSocket connection is established
    # PartialTranscript (Lower Latency) - This message is sent when AssemblyAI has transcribed the audio
    # FinalTranscript (Higher Accuracy) - This message is sent when AssemblyAI has transcribed and formatted the audio
    current_statement = ""
    try:
        while True:
            message = assembly_ws.recv()
            if not message:
                break
            message = json.loads(message)

            if message["message_type"] == "SessionBegins":
                session_id = message["session_id"]
                expires_at = message["expires_at"]
                print(f"Session ID: {session_id}")
                print(f"Expires at: {expires_at}")
            elif message["message_type"] == "PartialTranscript":
                global answering_question
                if not answering_question:
                    if len(message['text']) > 0:
                        current_statement = message['text']
                    else:
                        if len(current_statement) > 0:
                            answering_question = True
                            print(f"Question: {current_statement}")
                            response = ask(current_statement)
                            if response is not None:
                                speak(response)
                                current_statement = ""
            elif message["message_type"] == "FinalTranscript":
                if len(message['text']) > 0:
                    print(f"Transcript: {message['text']}")

    except websocket.WebSocketConnectionClosedException:
        print("WebSocket closed")
    except Exception as e:
        print(f"Error in handle_assembly_messages: {e}")


# Twilio Voice Request Handler
# This is the URL that Twilio will request when a call is received
# This route is used to initiate the call and start the WebSocket connection
@app.route('/call', methods=['POST'])
def call():
    """Accept a phone call."""
    response = VoiceResponse()
    start = Start()
    start.stream(url=f'wss://{request.host}/stream')
    response.append(start)
    response.say("Hello, how can I help you?")
    response.pause(length=60)
    print(request.form.get("CallSid"))
    global call_sid
    call_sid = request.form.get("CallSid")
    print(f'Incoming call from {request.form["From"]}')
    return str(response), 200, {'Content-Type': 'text/xml'}


# Twilio Voice Request Handler
# This text to speech route is used to update the call with new text to be spoken.
# The call is routed to this URL with the text to be spoken as a query parameter.
@app.route('/response', methods=['POST'])
def respond():
    """Accept a phone call."""
    response = VoiceResponse()
    start = Start()
    start.stream(url=f'wss://{request.host}/stream')
    response.append(start)
    response.say(request.args.get('text'))
    response.pause(length=60)
    return str(response), 200, {'Content-Type': 'text/xml'}

@sock.route('/stream')
def stream(ws):
    """Receive and transcribe audio stream."""
    # Set answering_question to False
    global answering_question
    answering_question = False
    # AssemblyAI WebSocket connection
    # AssemblyAI requires a sample rate of 16kHz
    sample_rate = 16000
    # AssemblyAI allows a list of words to boost that will be given a higher priority in the transcription
    word_boost = ["AssemblyAI"]
    params = {"sample_rate": sample_rate, "word_boost": json.dumps(word_boost)}
    assembly_ws = websocket.create_connection(
        f"wss://api.assemblyai.com/v2/realtime/ws?{urlencode(params)}",
        header={"Authorization": ASSEMBLYAI_API_KEY},
    )

    # Create a separate thread for handling incoming messages from AssemblyAI
    assembly_messages_thread = Thread(target=handle_assembly_messages, args=(assembly_ws,))
    assembly_messages_thread.start()

    audio_buffer = b""
    try:
        while True:
            message = ws.receive()
            packet = json.loads(message)
            if packet['event'] == 'start':
                print('Streaming is starting')
            elif packet['event'] == 'stop':
                print('\nStreaming has stopped')
            elif packet['event'] == 'media':
                # Convert the audio data from 8-bit ulaw to 16-bit PCM
                audio = base64.b64decode(packet['media']['payload'])
                audio = audioop.ulaw2lin(audio, 2)
                audio = audioop.ratecv(audio, 2, 1, 8000, 16000, None)[0]
                # Add the converted audio data to the buffer - Twilio sends 20ms of audio in each packet - AssemblyAI requires 120ms of audio to transcribe
                audio_buffer += audio
                # Calculate the duration of the buffered audio data in milliseconds
                audio_segment = AudioSegment.from_file(io.BytesIO(audio_buffer), format="raw", sample_width=2, channels=1, frame_rate=16000)
                duration_ms = len(audio_segment)
                # If the buffered audio data's duration is within the acceptable range, send it to AssemblyAI
                if 120 <= duration_ms <= 2000:
                    # Send the audio data to AssemblyAI
                    payload = {
                        "audio_data": base64.b64encode(audio_buffer).decode("utf-8")
                    }
                    assembly_ws.send(json.dumps(payload))
                    audio_buffer = b""  # Clear the buffer

    except ConnectionClosed:
        print("Connection closed")
    finally:
        # Close the AssemblyAI WebSocket connection
        assembly_ws.close()
        # Wait for the AssemblyAI messages handling thread to finish
        assembly_messages_thread.join()

if __name__ == '__main__':
    questions = []
    # Set CallSid to None, this will be used to track the call. Only one call can be used at a time.
    call_sid = None
    # Set conversation history to an empty list
    conversation_history = []
    # Set answering_question to False
    answering_question = False
    # Set the port to 5000 - this is the default port used by Flask - this should be reflected in the ngrok command
    port = 5000
    # Get the first phone number in the Twilio account - this is the number that will be used to receive calls
    number = twilio_client.incoming_phone_numbers.list()[0]
    print(f'Waiting for calls on {number.phone_number}')
    app.run(port=port)
  
