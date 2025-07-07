import requests
import os
from bs4 import BeautifulSoup
from urllib.parse import quote # Import quote for URL encoding

# Fallback to a general news scraping if NewsAPI key is not available or fails
# For this, we'll try to scrape Google News search results.
# Note: Scraping Google News can be unreliable due to changes in their HTML structure.
def scrape_google_news(query, max_articles=10):
    """
    Scrapes Google News for articles related to the query.
    This is a fallback and might be brittle.
    """
    articles = []
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36"
    }
    # URL encode the query
    encoded_query = quote(query + " IPO stock market sentiment")
    search_url = f"https://news.google.com/search?q={encoded_query}&hl=en-US&gl=US&ceid=US:en"

    # IMPORTANT: Scraping web pages, especially dynamic ones like Google News, is prone to breaking
    # if the website changes its HTML structure. This method is provided as a fallback
    # and may require updates if it stops working. Using official APIs is always more reliable.
    try:
        response = requests.get(search_url, headers=headers, timeout=10)
        response.raise_for_status()
        soup = BeautifulSoup(response.text, 'html.parser')

        # Google News structure can change. This is a common pattern:
        news_items = soup.find_all('article', limit=max_articles + 10) # fetch a bit more to filter

        count = 0
        for item in news_items:
            if count >= max_articles:
                break

            title_tag = item.find('h3')
            link_tag = item.find('a', href=True)
            # Sometimes the link is within the h3, sometimes it's a sibling or parent
            if link_tag and link_tag['href'].startswith('./articles/'): # Google News specific relative links
                 url = "https://news.google.com" + link_tag['href'][1:] # Construct absolute URL
            else:
                # Try finding any link within the article tag if the specific one isn't found
                links_in_item = item.find_all('a', href=True)
                if links_in_item:
                    # This is a heuristic, might pick up unwanted links
                    url = links_in_item[0]['href']
                    if not url.startswith('http'):
                         url = "https://news.google.com" + url # Assuming relative if not absolute
                else:
                    url = None

            title = title_tag.text if title_tag else "N/A"

            # Description/snippet often found in a sibling div or a specific class
            snippet_tag = item.find('div', jsname='RicRxf') # This jsname is often used for snippets
            description = snippet_tag.text if snippet_tag else ""

            if title != "N/A" and url:
                 # Basic filter: ensure query terms are in title or snippet
                if any(term.lower() in title.lower() for term in query.split()) or \
                   any(term.lower() in description.lower() for term in query.split()):
                    articles.append({
                        "title": title,
                        "url": url,
                        "description": description, # Snippet from search results
                        "content": description, # For now, use description as content
                        "source": {"name": "Google News"} # Source is Google News itself
                    })
                    count += 1

        if not articles:
            print(f"Google News scraping found no articles for '{query}' with current selectors.")

    except requests.RequestException as e:
        print(f"Error scraping Google News for '{query}': {e}")
    except Exception as ex:
        print(f"An unexpected error occurred during Google News scraping: {ex}")

    return articles[:max_articles]


def fetch_news_from_newsapi(query, api_key, max_articles=20):
    """
    Fetches news articles from NewsAPI.
    """
    articles = []
    # Add "IPO" and "stock" to the query to make it more specific for IPO sentiment
    search_query = f'"{query}" IPO OR stock sentiment'
    # NewsAPI endpoint for everything
    url = "https://newsapi.org/v2/everything"
    params = {
        'q': search_query,
        'language': 'en',
        'sortBy': 'relevancy', # Options: relevancy, popularity, publishedAt
        'pageSize': max_articles if max_articles <= 100 else 100, # Max 100 for NewsAPI
        'apiKey': api_key
    }
    try:
        response = requests.get(url, params=params, timeout=10)
        response.raise_for_status() # Raise an exception for HTTP errors
        data = response.json()
        articles = data.get('articles', [])
        # NewsAPI 'content' field is often truncated. 'description' can be a good summary.
        # We might need to fetch the full content from the article URL later if needed.
        print(f"Fetched {len(articles)} articles from NewsAPI for query: {query}")
    except requests.RequestException as e:
        print(f"NewsAPI request failed: {e}. Attempting fallback.")
        articles = [] # Ensure articles is empty if NewsAPI fails
    except Exception as ex:
        print(f"An unexpected error occurred with NewsAPI: {ex}. Attempting fallback.")
        articles = []

    return articles


def fetch_news_for_ipo(ipo_name, news_api_key, max_articles=30):
    """
    Fetches news articles for a given IPO name.
    Tries NewsAPI first, then falls back to Google News scraping if NewsAPI key is missing or fails.
    """
    fetched_articles = []
    use_news_api = bool(news_api_key)

    if use_news_api:
        print(f"Attempting to fetch news for '{ipo_name}' using NewsAPI.")
        fetched_articles = fetch_news_from_newsapi(ipo_name, news_api_key, max_articles)

    if not fetched_articles:
        if use_news_api: # Only print this if NewsAPI was attempted and failed
            print(f"NewsAPI failed or returned no articles for '{ipo_name}'. Falling back to Google News scraping.")
        else:
            print(f"NEWS_API_KEY not provided. Using Google News scraping for '{ipo_name}'.")

        # Ensure max_articles for scraper is reasonable, e.g. not more than 20-30 for performance
        scrape_max = min(max_articles, 20)
        fetched_articles = scrape_google_news(ipo_name, max_articles=scrape_max)

    if not fetched_articles:
        print(f"No articles found for '{ipo_name}' from any source.")
        return []

    # Basic filtering and content preparation
    # For now, we assume 'content' or 'description' from NewsAPI/Google News is good enough.
    # A more advanced step would be to fetch the actual URL and parse the full article text.

    # Ensure we don't exceed max_articles requested by the caller
    return fetched_articles[:max_articles]


def extract_text_from_html(html_content):
    """
    Extracts plain text from HTML content using BeautifulSoup.
    """
    if not html_content:
        return ""
    soup = BeautifulSoup(html_content, 'html.parser')

    # Remove script and style tags
    for script_or_style in soup(["script", "style"]):
        script_or_style.decompose()

    # Get text
    text = soup.get_text()

    # Break into lines and remove leading/trailing space on each
    lines = (line.strip() for line in text.splitlines())
    # Break multi-headlines into a line each
    chunks = (phrase.strip() for line in lines for phrase in line.split("  "))
    # Drop blank lines
    text = '\n'.join(chunk for chunk in chunks if chunk)

    return text

if __name__ == '__main__':
    # Example Usage (for testing this module directly)
    # You would need to set NEWS_API_KEY as an environment variable or pass it directly
    # For Google News scraping, no API key is needed.

    sample_ipo_name = "Reddit" # A recent example

    print(f"\n--- Testing with NewsAPI (if key is available) ---")
    api_key_from_env = os.environ.get('NEWS_API_KEY_FOR_TESTING') # Use a different var for direct testing

    if api_key_from_env:
        articles_newsapi = fetch_news_for_ipo(sample_ipo_name, api_key_from_env, max_articles=5)
        if articles_newsapi:
            for i, article in enumerate(articles_newsapi):
                print(f"\nArticle {i+1} (NewsAPI):")
                print(f"  Title: {article.get('title')}")
                print(f"  Source: {article.get('source', {}).get('name')}")
                print(f"  URL: {article.get('url')}")
                # print(f"  Description: {article.get('description')}")
                # print(f"  Content Snippet: {article.get('content')[:150] if article.get('content') else 'N/A'}...")
        else:
            print("No articles found via NewsAPI for the test.")
    else:
        print("NEWS_API_KEY_FOR_TESTING environment variable not set. Skipping direct NewsAPI test.")

    print(f"\n--- Testing with Google News Fallback ---")
    # Test without API key to force Google News scraping
    articles_gn_scrape = fetch_news_for_ipo(sample_ipo_name, None, max_articles=5)
    if articles_gn_scrape:
        for i, article in enumerate(articles_gn_scrape):
            print(f"\nArticle {i+1} (Google News):")
            print(f"  Title: {article.get('title')}")
            print(f"  Source: {article.get('source', {}).get('name')}")
            print(f"  URL: {article.get('url')}")
            # print(f"  Description: {article.get('description')}")
    else:
        print("No articles found via Google News scraping for the test.")

    # Example of HTML extraction (if you had raw HTML)
    # sample_html = "<html><head><title>Old Title</title><script>alert('bad')</script></head><body><p>This is <b>bold</b> text.</p> More text.</body></html>"
    # print(f"\n--- Testing HTML Extraction ---")
    # extracted = extract_text_from_html(sample_html)
    # print(extracted)
