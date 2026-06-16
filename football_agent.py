import anthropic

import os
from dotenv import load_dotenv
load_dotenv()
client = anthropic.Anthropic(api_key=os.environ.get("ANTHROPIC_API_KEY"))


conversation_history = []

def ask_agent(question):
    conversation_history.append({
        "role": "user",
        "content": question
    })
    
    response = client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=1000,
        system="You are an expert football analyst called FootballGPT. You specialise in comparing players and teams across different eras. Always give balanced, detailed analysis considering stats, context, era differences, and tactics. Remember previous messages in the conversation.",
        messages=conversation_history
    )
    
    answer = response.content[0].text
    
    conversation_history.append({
        "role": "assistant",
        "content": answer
    })
    
    return answer

if __name__ == "__main__":
    print("⚽ FootballGPT Ready! Type your question (or 'quit' to exit)")
    while True:
        question = input("\nYou: ").strip()
        if question.lower() == "quit":
            break
        if not question:
            print("Please type a question!")
            continue
        print("\nFootballGPT: ")
        answer = ask_agent(question)
        print(answer)
