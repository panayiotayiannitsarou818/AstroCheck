from openai import OpenAI

def generate_analysis(api_key: str, prompt: str, model: str = "gpt-5.4") -> str:
    client=OpenAI(api_key=api_key)
    response=client.responses.create(
        model=model,
        input=prompt,
        reasoning={"effort":"high"},
        text={"verbosity":"high"},
    )
    return response.output_text

