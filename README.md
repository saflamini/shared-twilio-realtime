# Realtime Phone Call Assistant

### Technology
- Telephony System + Text to Speech (Twilio)
- Realtime Speech to Text + Intelligence (AssemblyAI)

### Getting Setup
1. [Download ngrok](https://dashboard.ngrok.com/get-started/setup) 
2. Run ngrok on the http protocol on port 5000
3. [Create a Twilio account](https://console.twilio.com/)
4. [Create a Twilio Voice Phone Number](https://console.twilio.com/us1/develop/voice/overview)
5. [Create an AssemblyAI Account](https://www.assemblyai.com/app/)
6. Paste the appropriate API keys & NGROK_URL in the ```app.py``` file.
7. Run ```pip3 install -r requirements.txt```
8. Run ```python3 app.py```
9. Call the Twilio phone number you created

### Understanding Context & Data
```data.py``` & ```context.py``` can be used to prompt the Phone call Assistant.
In this example the context is provided via a variable ```prompt```. `data.py` contains info about the 'user' and `app.py` can be used to provide additional context - such as how the agent should behave, etc.

Feel free to get creative with the prompts!