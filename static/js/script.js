// =============================================
// ByaHero - Smart Commute AI
// Shared frontend helpers: form handling & predictions
// =============================================

// This file is loaded on every page. Only the commute-prediction page
// (#predictForm) uses it, so the handler must be registered conditionally —
// a null dereference here would otherwise break every other page's inline JS.
const predictForm = document.getElementById('predictForm');
const resultsSection = document.getElementById('resultsSection');
const errorSection = document.getElementById('errorSection');

// --- Weather widget in header ----------------------------------------------

async function loadHeaderWeather() {
    const weatherEl = document.getElementById('headerWeather');
    if (!weatherEl) return;

    try {
        const response = await fetch('/api/weather');
        const data = await response.json();

        if (data.success && data.weather && data.weather.length > 0) {
            // Use the first location (Kapatagan) as default weather
            const w = data.weather[0];
            const temp = Math.round(w.temperature_c);
            const icon = getWeatherIcon(w.weather_code);
            weatherEl.querySelector('.weather-icon').textContent = icon;
            weatherEl.querySelector('.weather-text').textContent = w.weather_text;
            weatherEl.setAttribute('data-temp', `${temp}°C`);
        } else {
            weatherEl.querySelector('.weather-icon').textContent = '🌤️';
            weatherEl.querySelector('.weather-text').textContent = 'No data';
        }
    } catch (error) {
        console.error('Error loading weather:', error);
        weatherEl.querySelector('.weather-icon').textContent = '🌤️';
        weatherEl.querySelector('.weather-text').textContent = 'Unavailable';
    }
}

function getWeatherIcon(code) {
    if (code === 0) return '☀️';
    if (code === 1) return '🌤️';
    if (code === 2) return '⛅';
    if (code === 3) return '☁️';
    if (code === 45 || code === 48) return '🌫️';
    if (code >= 51 && code <= 57) return '🌦️';
    if (code >= 61 && code <= 67) return '🌧️';
    if (code >= 71 && code <= 77) return '❄️';
    if (code >= 80 && code <= 82) return '🌦️';
    if (code >= 85 && code <= 86) return '🌨️';
    if (code >= 95) return '⛈️';
    return '🌤️';
}

// Initialize weather on page load
document.addEventListener('DOMContentLoaded', loadHeaderWeather);

// Refresh weather every 10 minutes
setInterval(loadHeaderWeather, 10 * 60 * 1000);

// --- Shared helpers -------------------------------------------------------

/** Show a panel that is hidden with an inline `style="display: none"`. */
function showPanel(el) {
    if (el) el.style.display = 'block';
}

/** Hide a panel. */
function hidePanel(el) {
    if (el) el.style.display = 'none';
}

/** Scroll an element into view without jumping the page on reduced-motion. */
function scrollToElement(el) {
    if (!el) return;
    const reduced = window.matchMedia &&
        window.matchMedia('(prefers-reduced-motion: reduce)').matches;
    el.scrollIntoView({ behavior: reduced ? 'auto' : 'smooth', block: 'start' });
}

/**
 * Escape a value for safe interpolation into innerHTML.
 * Arrival notes and location names are user-supplied, so they must not be
 * able to inject markup.
 */
function escapeHtml(value) {
    if (value === null || value === undefined) return '';
    return String(value)
        .replace(/&/g, '&amp;')
        .replace(/</g, '&lt;')
        .replace(/>/g, '&gt;')
        .replace(/"/g, '&quot;')
        .replace(/'/g, '&#39;');
}

/**
 * Get the user's timezone offset in minutes, so arrival records are
 * compared against the clock the user actually looked at rather than the
 * server's. The server usually runs in UTC, which is hours behind the user,
 * and every arrival the user recorded was then refused as being in the
 * future.
 */
async function estimate_timezone_offset() {
    try {
        const response = await fetch('/api/get-timezone');
        const data = await response.json();
        return data.tz_offset_minutes || 0;
    } catch (error) {
        console.error('Error estimating timezone:', error);
        return 0;
    }
}

/** Normalise a crowd level into a css class suffix: Low -> crowd-low. */
function crowdClass(level) {
    const key = String(level || '').toLowerCase();
    if (key === 'low' || key === 'medium' || key === 'high') return `crowd-${key}`;
    return 'crowd-unknown';
}

// --- Commute prediction ---------------------------------------------------

// Form submission handler
if (predictForm) {
    predictForm.addEventListener('submit', async (e) => {
        e.preventDefault();

        // Get form values
        const crowdInput = document.querySelector('input[name="crowd"]:checked');
        const formData = {
            route: document.getElementById('route').value,
            origin: document.getElementById('origin').value,
            stop: document.getElementById('stop').value,
            time: document.getElementById('time').value,
            day: document.getElementById('day').value,
            crowd: crowdInput ? crowdInput.value : ''
        };

        // Validate all fields are filled
        if (!formData.route || !formData.origin || !formData.stop || !formData.time || !formData.day || !formData.crowd) {
            showError('Please fill in all fields');
            return;
        }

        // Show loading state
        const submitBtn = predictForm.querySelector('.btn-predict, .btn-primary');
        const originalText = submitBtn ? submitBtn.textContent : '';
        if (submitBtn) {
            submitBtn.disabled = true;
            submitBtn.classList.add('loading');
            submitBtn.textContent = 'Calculating...';
        }

        try {
            // Send prediction request
            const response = await fetch('/api/predict', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                },
                body: JSON.stringify(formData)
            });

            const result = await response.json();

            if (result.success) {
                displayResults(result);
            } else {
                showError(result.error || 'Failed to get prediction');
            }
        } catch (error) {
            console.error('Error:', error);
            showError('An error occurred. Please try again.');
        } finally {
            // Restore button state
            if (submitBtn) {
                submitBtn.disabled = false;
                submitBtn.classList.remove('loading');
                submitBtn.textContent = originalText;
            }
        }
    });
}

// Populate the origin dropdown with the stops on the selected route
async function updateOrigins() {
    const routeId = document.getElementById('route').value;
    const originSelect = document.getElementById('origin');
    const stopSelect = document.getElementById('stop');

    if (!originSelect) return;

    originSelect.innerHTML = '<option value="">Select origin...</option>';
    originSelect.disabled = true;
    if (stopSelect) {
        stopSelect.innerHTML = '<option value="">Select destination...</option>';
        stopSelect.disabled = true;
    }

    if (!routeId) {
        if (stopSelect) stopSelect.disabled = false;
        return;
    }

    try {
        const response = await fetch(`/api/get-locations?route_id=${routeId}`);
        const data = await response.json();

        if (data.success) {
            data.locations.forEach(loc => {
                const option = document.createElement('option');
                option.value = loc.location_id;
                option.textContent = loc.name;
                originSelect.appendChild(option);
            });

            if (data.locations.length === 0) {
                const option = document.createElement('option');
                option.value = '';
                option.textContent = 'No stops on this route';
                option.disabled = true;
                originSelect.appendChild(option);
            }
        }
    } catch (error) {
        console.error('Error loading origins:', error);
    } finally {
        originSelect.disabled = false;
        if (stopSelect) stopSelect.disabled = false;
    }
}

// Populate the destination dropdown with the stops that come after the origin
async function updateDestinations() {
    const routeId = document.getElementById('route').value;
    const originId = document.getElementById('origin').value;
    const stopSelect = document.getElementById('stop');

    if (!stopSelect) return;

    stopSelect.innerHTML = '<option value="">Select destination...</option>';

    if (!routeId || !originId) return;

    // Disable the dropdown while it loads so a stale value can't be submitted.
    stopSelect.disabled = true;

    try {
        const response = await fetch(`/api/get-stops-after?route_id=${routeId}&stop_id=${originId}`);
        const data = await response.json();

        if (data.success) {
            data.stops.forEach(stop => {
                const option = document.createElement('option');
                option.value = stop.name;
                option.textContent = stop.name;
                stopSelect.appendChild(option);
            });

            if (data.stops.length === 0) {
                const option = document.createElement('option');
                option.value = '';
                option.textContent = 'No further stops on this route';
                option.disabled = true;
                stopSelect.appendChild(option);
            }
        }
    } catch (error) {
        console.error('Error loading destinations:', error);
    } finally {
        stopSelect.disabled = false;
    }
}

// Display results function
function displayResults(result) {
    // Hide error section
    hidePanel(errorSection);

    // Update travel time
    const travelTimeEl = document.getElementById('travelTimeResult') || document.getElementById('travelTime');
    if (travelTimeEl) travelTimeEl.textContent = `${result.travel_time} minutes`;

    // Update decision
    const decisionEl = document.getElementById('decisionResult');
    if (decisionEl) {
        if (result.decision === 'leave_now') {
            decisionEl.textContent = 'Leave Now';
            decisionEl.className = 'result-value decision urgent';
        } else {
            decisionEl.textContent = 'You Can Wait';
            decisionEl.className = 'result-value decision safe';
        }
    }

    // Update the trip summary
    const summaryEl = document.getElementById('tripSummary');
    if (summaryEl) {
        const parts = [];
        if (result.origin) parts.push(`From ${result.origin}`);
        if (result.destination) parts.push(`to ${result.destination}`);
        summaryEl.textContent = parts.join(' ');
    }

    // Generate insights
    const insightsEl = document.getElementById('insightsContent');
    if (insightsEl) {
        insightsEl.innerHTML = generateInsights(result);
    }

    // Show results section
    showPanel(resultsSection);
    scrollToElement(resultsSection);
}

// Generate insights based on prediction
function generateInsights(result) {
    const insights = [];

    // Travel time insight
    if (result.travel_time > 35) {
        insights.push('Long travel time expected. Plan accordingly.');
    } else if (result.travel_time > 20) {
        insights.push('Moderate travel time. Leave with enough buffer.');
    } else {
        insights.push('Quick route. You will arrive relatively soon.');
    }

    // Crowd level insight
    if (result.crowd === 'High') {
        insights.push('High crowd level. Bus may depart soon.');
    } else if (result.crowd === 'Medium') {
        insights.push('Moderate crowd. Standard travel conditions.');
    } else {
        insights.push('Low crowd. Comfortable travel expected.');
    }

    return insights.map(i => `<p class="insight-item">${escapeHtml(i)}</p>`).join('');
}

// Show error function
function showError(message) {
    showPanel(errorSection);
    const errorMessageEl = document.getElementById('errorMessage');
    if (errorMessageEl) errorMessageEl.textContent = message;
    hidePanel(resultsSection);
    scrollToElement(errorSection);
}

// Reset form function
function resetForm() {
    if (!predictForm) return;
    predictForm.reset();
    hidePanel(resultsSection);
    hidePanel(errorSection);

    const stopSelect = document.getElementById('stop');
    if (stopSelect) {
        stopSelect.innerHTML = '<option value="">Select destination...</option>';
        stopSelect.disabled = false;
    }

    const routeSelect = document.getElementById('route');
    if (routeSelect) routeSelect.focus();
}

// Initialize: Focus on first input on page load
window.addEventListener('load', () => {
    const routeSelect = document.getElementById('route');
    if (routeSelect) {
        // Populate the origin list if a route is already selected.
        if (routeSelect.value) {
            updateOrigins();
        }
        routeSelect.focus();
    }
});

// --- Splash screen --------------------------------------------------------

// Show the loading screen for one second, then fade it out and reveal the app.
// The splash markup is only rendered on the first page load of a session, so
// this is a no-op on every other panel.
const SPLASH_DURATION = 1000;

(function initSplash() {
    const splash = document.getElementById('splashScreen');
    if (!splash) return;

    const dismiss = () => {
        splash.classList.add('is-hidden');
        document.body.classList.remove('is-loading');
        // Keep it out of the way for anyone tabbing through the page.
        splash.setAttribute('aria-hidden', 'true');
    };

    // If anything goes wrong the app must still become usable, so the
    // timer is the only thing that gates the reveal.
    setTimeout(dismiss, SPLASH_DURATION);
})();

