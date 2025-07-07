import google.generativeai as genai
import os
import json
from collections import Counter

# Configure the Gemini API key
# This should be done once, ideally when the application starts.
# However, for modularity, we can ensure it's configured before making a call.
def configure_gemini(api_key):
    genai.configure(api_key=api_key)

def parse_gemini_response(text_response, article_title, article_url):
    """
    Parses the text response from Gemini, expecting a JSON-like string.
    Returns a dictionary with sentiment, highlights, and source info.
    """
    try:
        # Gemini's response might not be perfect JSON, so we try to guide it
        # and then parse defensively.
        # Expected format: {"sentiment": "Positive/Neutral/Negative", "positive_highlights": ["...", "..."], "negative_highlights": ["...", "..."], "key_buzzwords": ["...", "..."]}

        # Try to find JSON block if an explanation is included
        if '```json' in text_response:
            json_str = text_response.split('```json')[1].split('```')[0].strip()
        elif '```' in text_response: # Simpler ``` block without json specifier
             json_str = text_response.split('```')[1].split('```')[0].strip()
        else:
            json_str = text_response # Assume the whole response is the JSON string

        data = json.loads(json_str)

        sentiment = data.get("sentiment", "Neutral").capitalize()
        if sentiment not in ["Positive", "Neutral", "Negative"]:
            sentiment = "Neutral" # Default if invalid value

        return {
            "sentiment": sentiment,
            "positive_highlights": data.get("positive_highlights", []),
            "negative_highlights": data.get("negative_highlights", []),
            "key_buzzwords": data.get("key_buzzwords", []),
            "source_title": article_title,
            "source_url": article_url
        }
    except json.JSONDecodeError as e:
        print(f"JSONDecodeError parsing Gemini response: {e}")
        print(f"Problematic response part: {text_response[:500]}") # Log part of the response
        # Fallback if JSON parsing fails
        sentiment = "Neutral" # Default
        if "positive" in text_response.lower(): sentiment = "Positive"
        if "negative" in text_response.lower(): sentiment = "Negative"
        return {
            "sentiment": sentiment,
            "positive_highlights": [],
            "negative_highlights": [],
            "key_buzzwords": [],
            "error_parsing": True,
            "raw_response": text_response[:200], # include snippet of raw response for debugging
            "source_title": article_title,
            "source_url": article_url
        }
    except Exception as e:
        print(f"Unexpected error parsing Gemini response: {e}")
        return {
            "sentiment": "Neutral", # Default
            "positive_highlights": [],
            "negative_highlights": [],
            "key_buzzwords": [],
            "error_parsing": True,
            "raw_response": "Unexpected error during parsing.",
            "source_title": article_title,
            "source_url": article_url
        }


def analyze_batch_with_gemini(articles_data, gemini_api_key):
    """
    Analyzes a batch of articles using Gemini Pro.
    Each article_data in articles_data should be a dict with 'text', 'title', 'source_url'.
    Returns a list of sentiment analysis results for each article.
    """
    if not articles_data:
        return []

    configure_gemini(gemini_api_key)
    model = genai.GenerativeModel('gemini-pro')

    results = []

    # For now, process one by one. Batching can be complex with varying text lengths and ensuring
    # the model understands it's separate documents.
    # A single large prompt with all texts might exceed token limits or confuse the model.
    for article_info in articles_data:
        article_text = article_info.get("text", "")
        article_title = article_info.get("title", "N/A")
        article_url = article_info.get("source_url", "N/A")

        if not article_text.strip():
            results.append({
                "sentiment": "Neutral", # Or skip? For now, neutral for empty text.
                "positive_highlights": [],
                "negative_highlights": [],
                "key_buzzwords": [],
                "source_title": article_title,
                "source_url": article_url,
                "error": "Empty article text"
            })
            continue

        prompt = f"""\
Analyze the sentiment of the following news article regarding an IPO.
The company's name might be mentioned in the article.
Focus on the sentiment towards the IPO or the company in the context of its public offering.

Article Text:
---
{article_text[:3000]}
---

Based *only* on the text provided, classify the sentiment as "Positive", "Neutral", or "Negative".
Also, extract key positive highlights, key negative highlights, and general key buzzwords related to the IPO/company from the article.

Return your response ONLY as a JSON object with the following structure:
{{
  "sentiment": "...",
  "positive_highlights": ["...", "..."],
  "negative_highlights": ["...", "..."],
  "key_buzzwords": ["...", "..."]
}}
Ensure the highlights and buzzwords are concise phrases or terms.
If there are no specific positive or negative highlights, return an empty list for that field.
Do not include any explanations or text outside of this JSON structure.
"""
        try:
            # print(f"Sending to Gemini: {article_text[:100]}...") # For debugging
            response = model.generate_content(
                prompt,
                generation_config=genai.types.GenerationConfig(
                    # candidate_count=1, # Default is 1
                    # stop_sequences=['...'], # If needed
                    # max_output_tokens=2048, # Adjust as needed
                    temperature=0.3 # Lower temperature for more factual/deterministic output
                ),
                # safety_settings=[ # Adjust safety settings if defaults are too restrictive
                #     {"category": "HARM_CATEGORY_HARASSMENT","threshold": "BLOCK_NONE"},
                #     {"category": "HARM_CATEGORY_HATE_SPEECH","threshold": "BLOCK_NONE"},
                #     {"category": "HARM_CATEGORY_SEXUALLY_EXPLICIT","threshold": "BLOCK_NONE"},
                #     {"category": "HARM_CATEGORY_DANGEROUS_CONTENT","threshold": "BLOCK_NONE"},
                # ]
            )
            # print(f"Gemini Response Text: {response.text}") # For debugging
            parsed_result = parse_gemini_response(response.text, article_title, article_url)
            results.append(parsed_result)

        except Exception as e:
            print(f"Error calling Gemini API for article '{article_title}': {e}")
            if hasattr(e, 'response') and e.response: # type: ignore
                print(f"Gemini API Error Response: {e.response.prompt_feedback}") # type: ignore
            results.append({
                "sentiment": "Neutral", # Fallback sentiment
                "error": str(e),
                "source_title": article_title,
                "source_url": article_url
            })

    return results


def calculate_overall_sentiment(analysis_results):
    """
    Calculates overall sentiment score, breakdown, verdict, and aggregates highlights.
    analysis_results: A list of dicts, where each dict is the result from parse_gemini_response.
    """
    if not analysis_results:
        return {
            "sentiment_breakdown": {"Positive": 0, "Neutral": 0, "Negative": 0},
            "market_sentiment_score": 0,
            "verdict": "N/A",
            "aggregated_highlights": {"positive": [], "negative": []},
            "top_snippets": []
        }

    sentiments = [res.get("sentiment", "Neutral") for res in analysis_results if "error" not in res]
    sentiment_counts = Counter(sentiments)

    total_valid_articles = len(sentiments)
    if total_valid_articles == 0: # All articles might have had errors
        return {
            "sentiment_breakdown": {"Positive": 0, "Neutral": 0, "Negative": 0},
            "market_sentiment_score": 0, # Or some other indicator of failure
            "verdict": "Error in Analysis",
            "aggregated_highlights": {"positive": [], "negative": []},
            "top_snippets": []
        }

    positive_pct = (sentiment_counts.get("Positive", 0) / total_valid_articles) * 100
    neutral_pct = (sentiment_counts.get("Neutral", 0) / total_valid_articles) * 100
    negative_pct = (sentiment_counts.get("Negative", 0) / total_valid_articles) * 100

    # Score = ((Positive% × 5) + (Neutral% × 3) + (Negative% × 1))
    # The original formula divides by 100, but if we use percentages directly, it's implicitly handled.
    # Score = (positive_pct * 5 + neutral_pct * 3 + negative_pct * 1) / 100 -> if p_pct is 40, then 40*5 = 200.
    # Let's adjust to use the percentages as 0-100.
    # Score = ((Positive_Count * 5) + (Neutral_Count * 3) + (Negative_Count * 1)) / Total_Count
    # This way score is directly in 1-5 range if all articles are e.g. positive.

    # Corrected scoring:
    # score_numerator = (sentiment_counts.get("Positive", 0) * 5) + \
    #                   (sentiment_counts.get("Neutral", 0) * 3) + \
    #                   (sentiment_counts.get("Negative", 0) * 1)
    # market_sentiment_score = round(score_numerator / total_valid_articles, 2) if total_valid_articles > 0 else 0

    # Using the percentage-based formula from the prompt:
    # Score = ((Positive% × 5) + (Neutral% × 3) + (Negative% × 1)) ÷ 100
    market_sentiment_score = ((positive_pct * 5) + (neutral_pct * 3) + (negative_pct * 1)) / 100
    market_sentiment_score = round(market_sentiment_score, 2)


    verdict = "Neutral"
    if market_sentiment_score >= 4.0:
        verdict = "Strong Subscribe"
    elif market_sentiment_score >= 3.0:
        verdict = "Cautious Subscribe"
    elif market_sentiment_score < 2.0: # Implicitly, scores >= 2.0 and < 3.0 are Neutral
        verdict = "Avoid"
    # else it remains "Neutral" (i.e. 2.0 <= score < 3.0)

    # Aggregate highlights (simple aggregation for now, could be smarter)
    all_pos_highlights = []
    all_neg_highlights = []
    for res in analysis_results:
        if "error" not in res:
            all_pos_highlights.extend(res.get("positive_highlights", []))
            all_neg_highlights.extend(res.get("negative_highlights", []))

    # Get top N unique highlights (e.g., top 5)
    # For simplicity, just take the first few unique ones. A better way would be frequency count.
    unique_pos_highlights = list(dict.fromkeys(all_pos_highlights))[:5]
    unique_neg_highlights = list(dict.fromkeys(all_neg_highlights))[:5]

    # Prepare top snippets
    top_snippets = []
    for res in analysis_results:
        if "error" not in res:
            # Use buzzwords or a snippet of the article text if highlights are not detailed enough
            # For now, we'll use the article title and its sentiment as a "snippet" proxy
             top_snippets.append({
                "text": res.get("source_title", "Snippet N/A"),
                "sentiment": res.get("sentiment", "Neutral"),
                "source": res.get("source_url", "#")
            })
    # Sort snippets to show a mix or prioritize certain sentiments if needed
    # For now, just take the first 3-5 with their analyzed sentiment

    # Let's try to pick one of each sentiment for top_snippets if possible
    # then fill with whatever is available
    final_snippets = []
    seen_sentiments_for_snippets = set()

    # Prioritize Positive, then Negative, then Neutral for display diversity
    for sentiment_priority in ["Positive", "Negative", "Neutral"]:
        for res in analysis_results:
            if "error" not in res and res.get("sentiment") == sentiment_priority and sentiment_priority not in seen_sentiments_for_snippets:
                final_snippets.append({
                    "text": res.get("source_title", "N/A") + (": " + res.get("negative_highlights")[0] if sentiment_priority == "Negative" and res.get("negative_highlights") else "") + (": " + res.get("positive_highlights")[0] if sentiment_priority == "Positive" and res.get("positive_highlights") else ""),
                    "sentiment": res.get("sentiment"),
                    "source": res.get("source_url")
                })
                seen_sentiments_for_snippets.add(sentiment_priority)
                if len(final_snippets) >= 3: break
        if len(final_snippets) >= 3: break

    # If not enough diverse snippets, fill with remaining
    if len(final_snippets) < 3:
        for res in analysis_results:
            if "error" not in res and len(final_snippets) < 3:
                # Avoid adding duplicates if already picked
                is_already_added = any(snip["source"] == res.get("source_url") and snip["text"] == res.get("source_title") for snip in final_snippets) # Check text too
                if not is_already_added:
                    snippet_text_parts = [res.get("source_title", "N/A")]
                    if res.get("sentiment") == "Positive" and res.get("positive_highlights"):
                        snippet_text_parts.append(res.get("positive_highlights")[0])
                    elif res.get("sentiment") == "Negative" and res.get("negative_highlights"):
                        snippet_text_parts.append(res.get("negative_highlights")[0])

                    final_snippets.append({
                        "text": ": ".join(filter(None, snippet_text_parts)), # Join title and a highlight if available
                        "sentiment": res.get("sentiment"),
                        "source": res.get("source_url")
                    })


    return {
        "sentiment_breakdown": {
            "Positive": round(positive_pct,1),
            "Neutral": round(neutral_pct,1),
            "Negative": round(negative_pct,1)
        },
        "market_sentiment_score": market_sentiment_score,
        "verdict": verdict,
        "highlights": { # Renamed from aggregated_highlights for clarity
            "positive": unique_pos_highlights,
            "negative": unique_neg_highlights
        },
        "top_snippets": final_snippets[:3] # Ensure only top 3
    }

if __name__ == '__main__':
    # This is for direct testing of this module.
    # You need to set GOOGLE_API_KEY environment variable.
    print("Testing AI Analysis Module...")
    test_api_key = os.environ.get("GEMINI_API_KEY") # Ensure this is set for testing
    if not test_api_key:
        print("GEMINI_API_KEY environment variable not set. Cannot perform live Gemini test.")
    else:
        print(f"Using Gemini API Key: {'*' * (len(test_api_key)-4) + test_api_key[-4:]}")
        configure_gemini(test_api_key) # Configure with the key

        sample_articles_for_analysis = [
            {
                "text": "Excitement is building for the upcoming TechCorp IPO. Analysts predict strong opening day gains due to innovative technology and high pre-booking numbers. Demand is off the charts!",
                "title": "TechCorp IPO Soars with High Hopes",
                "source_url": "http://example.com/news1"
            },
            {
                "text": "While TechCorp shows promise, some market watchers are cautious. The current volatile market conditions and the company's high valuation present potential risks for investors. Regulatory hurdles also loom.",
                "title": "TechCorp IPO: A Mix of Promise and Peril",
                "source_url": "http://example.com/news2"
            },
            {
                "text": "The TechCorp IPO is just another tech offering. It has some standard features but nothing particularly groundbreaking. It will likely perform as per the market average.",
                "title": "TechCorp: A Standard IPO Offering",
                "source_url": "http://example.com/news3"
            },
            {
                "text": "Major concerns are being raised about TechCorp's leadership and their ability to navigate the competitive landscape post-IPO. Several key executives have recently departed, casting a shadow.",
                "title": "Leadership Woes Plague TechCorp Ahead of IPO",
                "source_url": "http://example.com/news4"
            }
        ]

        print(f"\nAnalyzing {len(sample_articles_for_analysis)} sample articles with Gemini Pro...")
        analysis_results = analyze_batch_with_gemini(sample_articles_for_analysis, test_api_key)

        print("\n--- Individual Article Analysis Results ---")
        if analysis_results:
            for i, result in enumerate(analysis_results):
                print(f"\nArticle {i+1}: {result.get('source_title')}")
                print(f"  Sentiment: {result.get('sentiment')}")
                if result.get('positive_highlights'): print(f"  Positive: {result.get('positive_highlights')}")
                if result.get('negative_highlights'): print(f"  Negative: {result.get('negative_highlights')}")
                if result.get('key_buzzwords'): print(f"  Buzzwords: {result.get('key_buzzwords')}")
                if result.get('error'): print(f"  Error: {result.get('error')}")
                if result.get('error_parsing'): print(f"  Parsing Error - Raw: {result.get('raw_response')}")

            print("\n--- Overall Calculated Sentiment ---")
            overall_sentiment_summary = calculate_overall_sentiment(analysis_results)
            print(json.dumps(overall_sentiment_summary, indent=2))
        else:
            print("No analysis results returned. Check for errors or API key issues.")

    # Test case for empty analysis results
    print("\n--- Testing with empty analysis results ---")
    empty_summary = calculate_overall_sentiment([])
    print(json.dumps(empty_summary, indent=2))

    # Test case for analysis results with errors
    print("\n--- Testing with analysis results containing errors ---")
    error_results = [
        {"error": "API call failed", "source_title": "Error Article 1", "source_url": "err1"},
        {"sentiment": "Positive", "source_title": "Good Article", "source_url": "good1"} # one good one
    ]
    error_summary = calculate_overall_sentiment(error_results)
    print(json.dumps(error_summary, indent=2))
