from flask import Flask, request, jsonify, render_template, make_response # Added make_response
import os
from datetime import datetime

# WeasyPrint import - will only be used if the library is installed
try:
    from weasyprint import HTML, CSS
    WEASYPRINT_AVAILABLE = True
except ImportError:
    WEASYPRINT_AVAILABLE = False
    print("Warning: WeasyPrint not installed. PDF export will not be available.")


app = Flask(__name__, template_folder='templates', static_folder='static')

# Configuration for Gemini API Key
# IMPORTANT: Store your API key in an environment variable or a secure config file.
# For now, we'll try to get it from an environment variable.
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY")
NEWS_API_KEY = os.environ.get("NEWS_API_KEY") # Added for NewsAPI

# Import data ingestion functions
from data_ingestion import fetch_news_for_ipo # extract_text_from_html is not directly used in app.py
# Import AI analysis functions
from ai_analysis import analyze_batch_with_gemini, calculate_overall_sentiment

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/api/sentiment', methods=['GET'])
def get_sentiment():
    ipo_name = request.args.get('ipo_name')
    if not ipo_name:
        return jsonify({"error": "ipo_name parameter is required"}), 400

    # NOTE: For actual Gemini analysis, we'll check GEMINI_API_KEY later,
    # right before calling Gemini. For data ingestion, we might need NEWS_API_KEY.

    # Mock data generation moved to a separate block for clarity,
    # will be triggered if actual data fetching or analysis fails AND in dev/test mode.
    def get_mock_data(company_name):
        print(f"Warning: API key missing or issue in data processing for {company_name}. Returning mock data.")
        mock_data = {
            "company_name": company_name,
            "ipo_date": "N/A (mock data)",
                "sentiment_breakdown": {"Positive": 40, "Neutral": 30, "Negative": 30},
                "market_sentiment_score": 3.5, # ((40*5) + (30*3) + (30*1)) / 100 = (200+90+30)/100 = 3.2 - corrected
                "verdict": "Cautious Subscribe",
                "highlights": {
                    "positive": ["Strong pre-booking.", "Innovative product line."],
                    "negative": ["High valuation concerns.", "Intense market competition."]
                },
                "top_snippets": [
                    {"text": "Investor enthusiasm is high for XYZ's upcoming IPO.", "sentiment": "Positive", "source": "NewsSiteA"},
                    {"text": "Analysts advise caution due to current market volatility affecting IPOs.", "sentiment": "Neutral", "source": "ReportBC"},
                    {"text": "Concerns about XYZ's debt load are surfacing pre-IPO.", "sentiment": "Negative", "source": "ForumPostX"}
                ]
            }
            # Recalculate score for mock data
            pos_pct = mock_data["sentiment_breakdown"]["Positive"]
            neu_pct = mock_data["sentiment_breakdown"]["Neutral"]
            neg_pct = mock_data["sentiment_breakdown"]["Negative"]
            score = ((pos_pct * 5) + (neu_pct * 3) + (neg_pct * 1)) / 100
            mock_data["market_sentiment_score"] = round(score, 2)

            if score >= 4.0:
                mock_data["verdict"] = "Strong Subscribe"
            elif score >= 3.0:
                mock_data["verdict"] = "Cautious Subscribe"
            elif score >= 2.0:
                mock_data["verdict"] = "Neutral"
            else:
                mock_data["verdict"] = "Avoid"
            return mock_data

    try:
        # Step 1: Fetch data
        if not NEWS_API_KEY and not (os.environ.get("FLASK_ENV") == "development" or os.environ.get("TESTING") == "True"):
            return jsonify({"error": "NEWS_API_KEY not configured on the server."}), 500

        raw_articles = fetch_news_for_ipo(ipo_name, NEWS_API_KEY, max_articles=30)

        if not raw_articles:
            if os.environ.get("FLASK_ENV") == "development" or os.environ.get("TESTING") == "True":
                return jsonify(get_mock_data(ipo_name))
            return jsonify({"error": "Could not fetch any articles for the IPO name."}), 404

        # Step 2: Extract text content (basic filtering is part of fetching and text extraction)
        # We'll aim to get a list of simple text strings for Gemini
        processed_texts = []
        for article in raw_articles:
            text_content = ""
            if article.get('content'): # NewsAPI often provides 'content'
                text_content = article['content']
            elif article.get('description'):
                text_content = article['description']

            # If we had full HTML, we'd use extract_text_from_html here
            # For NewsAPI, content is usually already somewhat clean.
            # A more robust solution would fetch URL and parse if content is truncated.
            if text_content:
                 # Basic relevance check - ensure IPO name is mentioned
                if ipo_name.lower() in text_content.lower():
                    processed_texts.append({
                        "text": text_content,
                        "source_url": article.get("url", "N/A"),
                        "title": article.get("title", "N/A")
                    })

        if not processed_texts:
            if os.environ.get("FLASK_ENV") == "development" or os.environ.get("TESTING") == "True":
                return jsonify(get_mock_data(ipo_name))
            return jsonify({"error": "No relevant articles found after filtering."}), 404

        # Placeholder for Gemini Analysis (Step 3)
        if not GEMINI_API_KEY:
            if os.environ.get("FLASK_ENV") == "development" or os.environ.get("TESTING") == "True":
                # Return mock data if Gemini key is missing in dev/test
                print("Warning: GEMINI_API_KEY not found. Cannot perform live Gemini Analysis. Returning mock data.")
                return jsonify(get_mock_data(ipo_name))
            else: # Not in dev/test, and no API Key
                app.logger.error("GEMINI_API_KEY not configured on the server for analysis.")
                return jsonify({"error": "AI Analysis service is not configured."}), 500

        # Step 3: Analyze with Gemini
        # `processed_texts` is a list of dicts: {"text": ..., "source_url": ..., "title": ...}
        # `analyze_batch_with_gemini` expects this structure.
        app.logger.info(f"Sending {len(processed_texts)} articles to Gemini for analysis for IPO: {ipo_name}")
        individual_analysis_results = analyze_batch_with_gemini(processed_texts, GEMINI_API_KEY)

        if not individual_analysis_results:
            app.logger.warn(f"Gemini analysis returned no results for {ipo_name}.")
            # Fallback to mock data if in dev/test, otherwise error
            if os.environ.get("FLASK_ENV") == "development" or os.environ.get("TESTING") == "True":
                return jsonify(get_mock_data(ipo_name))
            return jsonify({"error": "AI analysis failed to produce results."}), 500

        # Step 4: Calculate overall sentiment, score, verdict
        overall_sentiment_summary = calculate_overall_sentiment(individual_analysis_results)

        # Construct the final response
        final_response = {
            "company_name": ipo_name,
            "ipo_date": "N/A - (To be sourced or manually input)", # Placeholder
            "sentiment_breakdown": overall_sentiment_summary["sentiment_breakdown"],
            "market_sentiment_score": overall_sentiment_summary["market_sentiment_score"],
            "verdict": overall_sentiment_summary["verdict"],
            "highlights": overall_sentiment_summary["highlights"],
            "top_snippets": overall_sentiment_summary["top_snippets"],
            "source_article_count": len(processed_texts),
            # Optionally include individual analysis for debugging or more detailed view:
            # "detailed_analysis": individual_analysis_results
        }
        return jsonify(final_response)

    except Exception as e:
        app.logger.error(f"Critical error in get_sentiment for {ipo_name}: {e}", exc_info=True)
        # In case of any error during real processing, fallback to mock data in dev/test
        if os.environ.get("FLASK_ENV") == "development" or os.environ.get("TESTING") == "True":
            return jsonify(get_mock_data(ipo_name))
        return jsonify({"error": "An error occurred while processing your request."}), 500

# Internal function to get sentiment data, used by both JSON and PDF endpoints
def _get_sentiment_analysis_data(ipo_name_param):
    # This function encapsulates the logic from the original get_sentiment()
    # and returns the data dict or an error dict.

    # Data Ingestion
    if not NEWS_API_KEY and not (os.environ.get("FLASK_ENV") == "development" or os.environ.get("TESTING") == "True"):
        return {"error_message": "NEWS_API_KEY not configured on the server.", "status_code": 500}

    raw_articles = fetch_news_for_ipo(ipo_name_param, NEWS_API_KEY, max_articles=30)

    if not raw_articles:
        if os.environ.get("FLASK_ENV") == "development" or os.environ.get("TESTING") == "True":
            return get_mock_data(ipo_name_param) # Returns mock data directly
        return {"error_message": "Could not fetch any articles for the IPO name.", "status_code": 404}

    processed_texts = []
    for article in raw_articles:
        text_content = article.get('content') or article.get('description', "")
        if text_content and ipo_name_param.lower() in text_content.lower():
            processed_texts.append({
                "text": text_content,
                "source_url": article.get("url", "N/A"),
                "title": article.get("title", "N/A")
            })

    if not processed_texts:
        if os.environ.get("FLASK_ENV") == "development" or os.environ.get("TESTING") == "True":
            return get_mock_data(ipo_name_param)
        return {"error_message": "No relevant articles found after filtering.", "status_code": 404}

    # AI Analysis
    if not GEMINI_API_KEY:
        if os.environ.get("FLASK_ENV") == "development" or os.environ.get("TESTING") == "True":
            print("Warning: GEMINI_API_KEY not found for analysis. Returning mock data.")
            return get_mock_data(ipo_name_param)
        else:
            app.logger.error("GEMINI_API_KEY not configured for analysis.")
            return {"error_message": "AI Analysis service is not configured.", "status_code": 500}

    app.logger.info(f"Sending {len(processed_texts)} articles to Gemini for analysis for IPO: {ipo_name_param}")
    individual_analysis_results = analyze_batch_with_gemini(processed_texts, GEMINI_API_KEY)

    if not individual_analysis_results:
        app.logger.warn(f"Gemini analysis returned no results for {ipo_name_param}.")
        if os.environ.get("FLASK_ENV") == "development" or os.environ.get("TESTING") == "True":
            return get_mock_data(ipo_name_param)
        return {"error_message": "AI analysis failed to produce results.", "status_code": 500}

    overall_sentiment_summary = calculate_overall_sentiment(individual_analysis_results)

    return {
        "company_name": ipo_name_param,
        "ipo_date": "N/A - (To be sourced or manually input)",
        "sentiment_breakdown": overall_sentiment_summary["sentiment_breakdown"],
        "market_sentiment_score": overall_sentiment_summary["market_sentiment_score"],
        "verdict": overall_sentiment_summary["verdict"],
        "highlights": overall_sentiment_summary["highlights"],
        "top_snippets": overall_sentiment_summary["top_snippets"],
        "source_article_count": len(processed_texts),
    }

@app.route('/api/sentiment/pdf', methods=['GET'])
def get_sentiment_pdf():
    if not WEASYPRINT_AVAILABLE:
        return jsonify({"error": "PDF generation service is not available (WeasyPrint not installed)."}), 501

    ipo_name = request.args.get('ipo_name')
    if not ipo_name:
        return jsonify({"error": "ipo_name parameter is required"}), 400

    try:
        analysis_data = _get_sentiment_analysis_data(ipo_name)
        if analysis_data.get("error_message"): # Check if our internal helper returned an error structure
             return jsonify({"error": analysis_data["error_message"]}), analysis_data.get("status_code", 500)

        # Render HTML template for PDF
        generation_date_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S UTC")
        html_for_pdf = render_template('pdf_template.html', data=analysis_data, generation_date=generation_date_str)

        # Create PDF
        # Base URL is needed for WeasyPrint to find static assets if linked in template (not strictly needed for this basic template)
        pdf_bytes = HTML(string=html_for_pdf, base_url=request.url_root).write_pdf()

        response = make_response(pdf_bytes)
        response.headers['Content-Type'] = 'application/pdf'
        response.headers['Content-Disposition'] = f'attachment; filename="{ipo_name}_sentiment_report.pdf"'
        return response

    except Exception as e:
        app.logger.error(f"Error generating PDF for {ipo_name}: {e}", exc_info=True)
        return jsonify({"error": "An error occurred while generating the PDF report."}), 500


if __name__ == '__main__':
    # It's good practice to make host and port configurable,
    # but for simplicity, we'll hardcode for now.
    # Use 0.0.0.0 to make it accessible externally if needed (e.g., in a container)
    app.run(host='0.0.0.0', port=5000, debug=True)
