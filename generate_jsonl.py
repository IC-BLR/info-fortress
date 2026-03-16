import json
import random

SYSTEM_PROMPT = "You are an information integrity analyst. Return strict JSON only."

conspiracy_phrases = [
    "Secret elites controlling global food supplies",
    "Microchips hidden inside vaccines",
    "Election officials secretly altering vote totals",
    "5G towers manipulating human thoughts",
    "Hidden global cabal influencing markets",
]

panic_phrases = [
    "SHOCK: Banks freezing accounts nationwide",
    "URGENT: Government seizing private savings",
    "BREAKING: Economy collapsing overnight",
    "ALERT: Massive financial lockdown begins tomorrow",
]

credible_phrases = [
    "Reuters reports GDP growth of 2.1%",
    "IMF projects modest economic slowdown",
    "Nature study confirms treatment efficacy",
    "Central bank announces interest rate increase",
]

anonymous_expert_phrases = [
    "Experts predict economic crash",
    "Insiders warn policy will destroy jobs",
    "Analysts say housing market collapse imminent",
]

satire_phrases = [
    "The Onion says aliens built pyramids",
    "Satire blog claims pigeons are spy drones",
    "Comedy site reports Congress bans Mondays",
]

categories = [
    (conspiracy_phrases, 90, "likely_false", "conspiracy_theory"),
    (panic_phrases, 85, "likely_false", "panic_claim"),
    (credible_phrases, 10, "likely_true", "breaking_news"),
    (anonymous_expert_phrases, 55, "uncertain", "economic_forecast"),
    (satire_phrases, 12, "satire", "satire"),
]

def generate_example(text, risk, veracity, article_type):
    return {
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": text},
            {"role": "assistant", "content": json.dumps({
                "risk_score": risk,
                "veracity_assessment": veracity,
                "article_type": article_type,
                "confidence": round(random.uniform(0.8, 0.99), 2),
                "indicators": ["structural signal detected"],
                "summary": "Structured integrity assessment."
            })}
        ]
    }

dataset = []

for _ in range(100):
    for phrase_group, risk, veracity, article_type in categories:
        text = random.choice(phrase_group)
        # add random noise for diversity
        noise = random.choice([
            "",
            " according to unnamed sources.",
            " with no official documentation.",
            " as claimed in viral posts.",
            " though no primary documents exist.",
        ])
        dataset.append(generate_example(text + noise, risk, veracity, article_type))

with open("structural_integrity_500.jsonl", "w") as f:
    for item in dataset:
        f.write(json.dumps(item) + "\n")

print("500-example dataset generated successfully.")