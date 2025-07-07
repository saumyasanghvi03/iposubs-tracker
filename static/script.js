document.addEventListener('DOMContentLoaded', () => {
    const ipoNameInput = document.getElementById('ipoNameInput');
    const searchButton = document.getElementById('searchButton');
    const resultsContainer = document.getElementById('resultsContainer');
    const loadingIndicator = document.getElementById('loadingIndicator');
    const errorDisplay = document.getElementById('errorDisplay');
    const errorMessageElement = document.getElementById('errorMessage');
    const analysisResultsDiv = document.getElementById('analysisResults');

    // Result display elements
    const companyNameDisplay = document.getElementById('companyNameDisplay');
    const ipoDateDisplay = document.getElementById('ipoDateDisplay');
    const marketSentimentScoreDisplay = document.getElementById('marketSentimentScore');
    const verdictBadge = document.getElementById('verdictBadge');
    const positiveHighlightsList = document.getElementById('positiveHighlightsList');
    const negativeHighlightsList = document.getElementById('negativeHighlightsList');
    const topSnippetsList = document.getElementById('topSnippetsList');
    const sentimentPieChartCanvas = document.getElementById('sentimentPieChart');
    const downloadPdfButton = document.getElementById('downloadPdfButton');
    let sentimentPieChart = null; // To store the Chart.js instance
    let currentIpoName = ""; // Store the current IPO name for PDF download

    searchButton.addEventListener('click', fetchSentimentData);
    ipoNameInput.addEventListener('keypress', (event) => {
        if (event.key === 'Enter') {
            fetchSentimentData();
        }
    });

    downloadPdfButton.addEventListener('click', () => {
        if (currentIpoName) {
            // Open in new tab, browser will handle download
            window.open(`/api/sentiment/pdf?ipo_name=${encodeURIComponent(currentIpoName)}`, '_blank');
        } else {
            showError("Please perform a sentiment analysis first to download PDF.");
        }
    });

    async function fetchSentimentData() {
        currentIpoName = ipoNameInput.value.trim(); // Store/update current IPO name
        if (!currentIpoName) {
            showError("Please enter an IPO/Company name.");
            downloadPdfButton.classList.add('hidden');
            return;
        }

        showLoading(true);
        hideError();
        resultsContainer.classList.add('hidden');
        downloadPdfButton.classList.add('hidden'); // Hide PDF button during load

        try {
            const response = await fetch(`/api/sentiment?ipo_name=${encodeURIComponent(ipoName)}`);
            showLoading(false);

            if (!response.ok) {
                let errorMsg = `Error: ${response.status} ${response.statusText}`;
                try {
                    const errorData = await response.json();
                    errorMsg = errorData.error || errorMsg;
                } catch (e) { /* Ignore if error response is not JSON */ }
                showError(errorMsg);
                return;
            }

            const data = await response.json();
            displaySentimentData(data);
            resultsContainer.classList.remove('hidden');
            analysisResultsDiv.classList.remove('hidden');
            if (data && !data.error) { // Show PDF button only if data is successfully loaded
                downloadPdfButton.classList.remove('hidden');
            } else {
                downloadPdfButton.classList.add('hidden');
            }

        } catch (error) {
            console.error("Fetch error:", error);
            showLoading(false);
            showError("An error occurred while fetching data. Check console for details.");
            downloadPdfButton.classList.add('hidden');
        }
    }

    function showLoading(isLoading) {
        if (isLoading) {
            loadingIndicator.classList.remove('hidden');
            analysisResultsDiv.classList.add('hidden');
            downloadPdfButton.classList.add('hidden'); // Also hide PDF button when loading new data
        } else {
            loadingIndicator.classList.add('hidden');
        }
    }

    function showError(message) {
        errorMessageElement.textContent = message;
        errorDisplay.classList.remove('hidden');
        analysisResultsDiv.classList.add('hidden');
        downloadPdfButton.classList.add('hidden'); // Hide PDF button on error
    }

    function hideError() {
        errorDisplay.classList.add('hidden');
    }

    function displaySentimentData(data) {
        companyNameDisplay.textContent = data.company_name || "N/A";
        ipoDateDisplay.textContent = data.ipo_date || "N/A";
        marketSentimentScoreDisplay.textContent = data.market_sentiment_score !== undefined ? data.market_sentiment_score.toFixed(2) : "N/A";

        updateVerdictBadge(data.verdict);

        updateHighlightsList(positiveHighlightsList, data.highlights?.positive || []);
        updateHighlightsList(negativeHighlightsList, data.highlights?.negative || []);

        updateTopSnippetsList(data.top_snippets || []);

        renderPieChart(data.sentiment_breakdown || { Positive: 0, Neutral: 0, Negative: 0 });
    }

    function updateVerdictBadge(verdict) {
        verdictBadge.textContent = verdict || "N/A";
        verdictBadge.className = 'badge'; // Reset classes
        if (verdict) {
            verdictBadge.classList.add(verdict.toLowerCase().replace(/\s+/g, '-'));
        } else {
            verdictBadge.classList.add('na');
        }
    }

    function updateHighlightsList(ulElement, highlights) {
        ulElement.innerHTML = ''; // Clear previous
        if (highlights.length === 0) {
            ulElement.innerHTML = '<li>No specific highlights found.</li>';
            return;
        }
        highlights.forEach(item => {
            const li = document.createElement('li');
            li.textContent = item;
            ulElement.appendChild(li);
        });
    }

    function updateTopSnippetsList(snippets) {
        topSnippetsList.innerHTML = ''; // Clear previous
        if (snippets.length === 0) {
            topSnippetsList.innerHTML = '<li>No snippets available.</li>';
            return;
        }
        snippets.forEach(snippet => {
            const li = document.createElement('li');

            const sentimentIndicator = document.createElement('span');
            sentimentIndicator.className = `sentiment-indicator ${snippet.sentiment?.toLowerCase() || 'neutral'}`;

            const textSpan = document.createElement('span');
            textSpan.className = 'snippet-text';
            textSpan.textContent = snippet.text || "N/A";

            const sourceDiv = document.createElement('div');
            sourceDiv.className = 'snippet-source';
            if (snippet.source && snippet.source !== '#') {
                const sourceLink = document.createElement('a');
                sourceLink.href = snippet.source;
                sourceLink.textContent = `Source: ${new URL(snippet.source).hostname}`; // Show domain
                sourceLink.target = "_blank";
                sourceDiv.appendChild(sourceLink);
            } else {
                sourceDiv.textContent = "Source: N/A";
            }

            li.appendChild(sentimentIndicator);
            li.appendChild(textSpan);
            li.appendChild(sourceDiv);
            topSnippetsList.appendChild(li);
        });
    }

    function renderPieChart(sentimentBreakdown) {
        if (sentimentPieChart) {
            sentimentPieChart.destroy(); // Destroy existing chart before rendering new one
        }

        const data = {
            labels: ['Positive', 'Neutral', 'Negative'],
            datasets: [{
                label: 'Sentiment Breakdown',
                data: [
                    sentimentBreakdown.Positive || 0,
                    sentimentBreakdown.Neutral || 0,
                    sentimentBreakdown.Negative || 0
                ],
                backgroundColor: [
                    'rgba(46, 204, 113, 0.7)',  // Positive (Green)
                    'rgba(149, 165, 166, 0.7)', // Neutral (Grey)
                    'rgba(231, 76, 60, 0.7)'   // Negative (Red)
                ],
                borderColor: [
                    'rgba(39, 174, 96, 1)',
                    'rgba(127, 140, 141, 1)',
                    'rgba(192, 57, 43, 1)'
                ],
                borderWidth: 1
            }]
        };

        const config = {
            type: 'pie',
            data: data,
            options: {
                responsive: true,
                maintainAspectRatio: false, // Allow chart to fill container better
                plugins: {
                    legend: {
                        position: 'top',
                    },
                    tooltip: {
                        callbacks: {
                            label: function(context) {
                                let label = context.label || '';
                                if (label) {
                                    label += ': ';
                                }
                                if (context.parsed !== null) {
                                    label += context.parsed.toFixed(1) + '%';
                                }
                                return label;
                            }
                        }
                    }
                }
            }
        };

        if (sentimentPieChartCanvas) {
            sentimentPieChart = new Chart(sentimentPieChartCanvas, config);
        } else {
            console.error("Pie chart canvas element not found!");
        }
    }
});
