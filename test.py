from ollama import chat

stream = chat(
    model='gemma3:1b',
    messages=[{'role': 'user', 'content': 'Why is the sky blue?'}],
    stream=False,
)

for chunk in stream:
    print(chunk['message']['content'], end='', flush=True)