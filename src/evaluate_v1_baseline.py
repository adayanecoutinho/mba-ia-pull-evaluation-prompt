"""
Script auxiliar (NÃO faz parte do desafio, não substitui evaluate.py).

Mede a linha de base do prompt v1 (baixa qualidade) com as mesmas 5 métricas
usadas em evaluate.py, apenas para gerar números REAIS para a tabela
comparativa v1 vs v2 do README — em vez de usar os valores ilustrativos do
enunciado, que não são uma medição de verdade.

Diferença em relação a evaluate.py: em vez de puxar o prompt do LangSmith
Hub, monta o ChatPromptTemplate diretamente a partir do arquivo local
prompts/bug_to_user_story_v1.yml (não é necessário publicar o v1 no Hub).

Não altera evaluate.py, metrics.py, utils.py nem o dataset — só importa
funções deles.
"""

import os
import sys
from pathlib import Path
from dotenv import load_dotenv
from langchain_core.prompts import ChatPromptTemplate
from langsmith import Client

from utils import load_yaml, check_env_vars, print_section_header
from evaluate import (
    load_dataset_from_jsonl,
    create_evaluation_dataset,
    evaluate_prompt_on_example,
    display_results,
    get_llm,
)
from metrics import evaluate_f1_score, evaluate_clarity, evaluate_precision

load_dotenv()


def build_v1_prompt_template() -> ChatPromptTemplate:
    data = load_yaml("prompts/bug_to_user_story_v1.yml")
    if not data:
        raise RuntimeError("Não foi possível carregar prompts/bug_to_user_story_v1.yml")

    prompt_key = next(iter(data))
    prompt_data = data[prompt_key]

    return ChatPromptTemplate.from_messages(
        [
            ("system", prompt_data["system_prompt"]),
            ("human", prompt_data["user_prompt"]),
        ]
    )


def main():
    print_section_header("BASELINE: AVALIANDO O PROMPT V1 (BAIXA QUALIDADE)")

    provider = os.getenv("LLM_PROVIDER", "openai")
    required_vars = ["LANGSMITH_API_KEY"]
    if provider == "openai":
        required_vars.append("OPENAI_API_KEY")
    elif provider in ["google", "gemini"]:
        required_vars.append("GOOGLE_API_KEY")

    if not check_env_vars(required_vars):
        return 1

    client = Client()
    project_name = os.getenv("LANGSMITH_PROJECT", "prompt-optimization-challenge-resolved")
    jsonl_path = "datasets/bug_to_user_story.jsonl"

    if not Path(jsonl_path).exists():
        print(f"❌ Arquivo de dataset não encontrado: {jsonl_path}")
        return 1

    dataset_name = f"{project_name}-eval"
    create_evaluation_dataset(client, dataset_name, jsonl_path)

    prompt_template = build_v1_prompt_template()
    examples = list(client.list_examples(dataset_name=dataset_name))
    print(f"   Dataset: {len(examples)} exemplos")

    llm = get_llm()

    f1_scores, clarity_scores, precision_scores = [], [], []

    print("   Avaliando exemplos...")
    for i, example in enumerate(examples, 1):
        result = evaluate_prompt_on_example(prompt_template, example, llm)

        if result["answer"]:
            f1 = evaluate_f1_score(result["question"], result["answer"], result["reference"])
            clarity = evaluate_clarity(result["question"], result["answer"], result["reference"])
            precision = evaluate_precision(result["question"], result["answer"], result["reference"])

            f1_scores.append(f1["score"])
            clarity_scores.append(clarity["score"])
            precision_scores.append(precision["score"])

            print(
                f"      [{i}/{len(examples)}] "
                f"F1:{f1['score']:.2f} Clarity:{clarity['score']:.2f} Precision:{precision['score']:.2f}"
            )

    avg_f1 = sum(f1_scores) / len(f1_scores) if f1_scores else 0.0
    avg_clarity = sum(clarity_scores) / len(clarity_scores) if clarity_scores else 0.0
    avg_precision = sum(precision_scores) / len(precision_scores) if precision_scores else 0.0
    avg_helpfulness = (avg_clarity + avg_precision) / 2
    avg_correctness = (avg_f1 + avg_precision) / 2

    scores = {
        "helpfulness": round(avg_helpfulness, 4),
        "correctness": round(avg_correctness, 4),
        "f1_score": round(avg_f1, 4),
        "clarity": round(avg_clarity, 4),
        "precision": round(avg_precision, 4),
    }

    display_results("bug_to_user_story_v1 (baseline local, não publicado no Hub)", scores)
    return 0


if __name__ == "__main__":
    sys.exit(main())
