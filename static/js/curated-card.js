(function () {
  const dataNode = document.getElementById('curated-card-page-data');
  if (!dataNode) return;

  let pageData = {};
  try {
    pageData = JSON.parse(dataNode.textContent || '{}');
  } catch (error) {
    console.error('Failed to parse curated card page data', error);
    return;
  }

  const body = document.body;
  const fullCardLink = document.querySelector('[data-route-path][href][class*="is-full-card"]');
  const routeLinks = Array.from(document.querySelectorAll('[data-route-link][data-route-path]'));
  const panels = Array.from(document.querySelectorAll('.race-panel[data-race]'));
  const heroSubtitle = document.getElementById('cc-hero-subtitle');
  const viewChip = document.getElementById('cc-view-chip');

  const normalizePath = (path) => (path && path !== '/' ? path.replace(/\/+$/, '') : path || '/');
  const routeIndex = new Map();
  const fullCardRoute = pageData.fullCard || {};
  routeIndex.set(normalizePath(fullCardRoute.path), fullCardRoute);
  Object.values(pageData.races || {}).forEach((route) => routeIndex.set(normalizePath(route.path), route));

  const setAttr = (selector, attribute, value) => {
    const node = document.querySelector(selector);
    if (node && value) node.setAttribute(attribute, value);
  };

  const buildDetail = (route) => ({
    path: route.path,
    absoluteUrl: route.absolute_url,
    title: route.title,
    description: route.description,
    viewMode: route.view_mode,
    raceNumber: route.race_number || null,
    trackId: pageData.trackId,
    trackName: pageData.trackName,
    trackSlug: pageData.trackSlug,
    raceDate: pageData.raceDate,
  });

  const dispatchVirtualPageView = (route) => {
    const detail = buildDetail(route);
    window.trackstarPageContext = detail;
    window.dispatchEvent(new CustomEvent('trackstar:virtual-pageview', { detail }));
    if (Array.isArray(window.dataLayer)) {
      window.dataLayer.push({ event: 'virtual_page_view', ...detail, page_path: detail.path, page_title: detail.title });
    }
    if (typeof window.gtag === 'function') {
      window.gtag('event', 'page_view', {
        page_title: detail.title,
        page_location: detail.absoluteUrl,
        page_path: detail.path,
      });
    }
  };

  const refreshAds = (route) => {
    const detail = buildDetail(route);
    window.dispatchEvent(new CustomEvent('trackstar:ads-refresh', { detail }));
    if (window.googletag && typeof window.googletag.pubads === 'function') {
      window.googletag.cmd = window.googletag.cmd || [];
      window.googletag.cmd.push(() => {
        const slots = Array.isArray(window.trackstarAdSlots) && window.trackstarAdSlots.length ? window.trackstarAdSlots : undefined;
        window.googletag.pubads().refresh(slots);
      });
    }
  };

  const updateRouteUI = (route) => {
    const detail = buildDetail(route);
    body.dataset.viewMode = detail.viewMode;
    body.dataset.selectedRace = detail.raceNumber || '';
    document.title = detail.title;
    setAttr('#meta-description', 'content', detail.description);
    setAttr('#canonical-link', 'href', detail.absoluteUrl);
    setAttr('#og-type', 'content', detail.viewMode === 'race' ? 'article' : 'website');
    setAttr('#og-title', 'content', detail.title);
    setAttr('#og-description', 'content', detail.description);
    setAttr('#og-url', 'content', detail.absoluteUrl);
    setAttr('#twitter-title', 'content', detail.title);
    setAttr('#twitter-description', 'content', detail.description);
    if (heroSubtitle) {
      heroSubtitle.textContent = detail.viewMode === 'race' && detail.raceNumber
        ? `Focused strategy and instant race-level routing for Race ${detail.raceNumber}.`
        : 'Laid-back picks and sharp strategy for every race on the card.';
    }
    if (viewChip) {
      viewChip.textContent = detail.viewMode === 'race' && detail.raceNumber
        ? `🏇 Race ${detail.raceNumber} View`
        : '📖 Full Card View';
    }

    routeLinks.forEach((link) => {
      const path = normalizePath(link.dataset.routePath);
      const isActive = path === normalizePath(detail.path);
      link.classList.toggle('is-active', isActive);
      if (isActive) link.setAttribute('aria-current', 'page');
      else link.removeAttribute('aria-current');
    });

    panels.forEach((panel) => {
      const raceNumber = Number(panel.dataset.race);
      const isActive = detail.viewMode === 'full-card' || raceNumber === detail.raceNumber;
      panel.classList.toggle('is-active', isActive);
    });
  };

  let activePath = normalizePath(window.location.pathname);
  const applyRoute = (route, { push = false, track = true, scroll = true } = {}) => {
    if (!route) return;
    const nextPath = normalizePath(route.path);
    const routeChanged = nextPath !== activePath;
    updateRouteUI(route);
    if (push && routeChanged) history.pushState({ path: nextPath }, '', route.path);
    if (track && routeChanged) {
      dispatchVirtualPageView(route);
      refreshAds(route);
    }
    if (scroll) {
      if (route.view_mode === 'race' && route.race_number) {
        document.getElementById(`race-panel-${route.race_number}`)?.scrollIntoView({ behavior: 'smooth', block: 'start' });
      } else {
        window.scrollTo({ top: 0, behavior: 'smooth' });
      }
    }
    activePath = nextPath;
  };

  document.addEventListener('click', (event) => {
    const link = event.target.closest('[data-route-link][data-route-path]');
    if (!link || event.defaultPrevented || event.metaKey || event.ctrlKey || event.shiftKey || event.altKey) return;
    const route = routeIndex.get(normalizePath(link.dataset.routePath));
    if (!route) return;
    event.preventDefault();
    applyRoute(route, { push: true, track: true, scroll: true });
  });

  window.addEventListener('popstate', () => {
    const route = routeIndex.get(normalizePath(window.location.pathname));
    if (route) applyRoute(route, { push: false, track: true, scroll: false });
  });

  window.toggleOverview = function toggleOverview(btn) {
    const bodyNode = document.getElementById('overview-body');
    if (!bodyNode) return;
    bodyNode.classList.toggle('is-expanded');
    btn.textContent = bodyNode.classList.contains('is-expanded') ? 'Show less' : 'Show more';
  };

  window.switchTab = function switchTab(clickedTab, contentId) {
    const tabsContainer = clickedTab.parentElement;
    const drilldownContainer = tabsContainer.parentElement;
    tabsContainer.querySelectorAll('.dd-tab').forEach((tab) => tab.classList.remove('tab-active'));
    drilldownContainer.querySelectorAll('.dd-content').forEach((content) => content.classList.remove('tab-active'));
    clickedTab.classList.add('tab-active');
    document.getElementById(contentId)?.classList.add('tab-active');
  };

  window.copyStrategy = function copyStrategy(raceNum, btn) {
    const strategySpan = document.getElementById(`strategy-text-${raceNum}`);
    if (!strategySpan) return;
    navigator.clipboard.writeText(strategySpan.innerText || strategySpan.textContent || '').then(() => {
      const originalText = btn.textContent;
      btn.textContent = '✓ Copied';
      window.setTimeout(() => { btn.textContent = originalText; }, 1500);
    }).catch((error) => console.error('Failed to copy text:', error));
  };

  if (fullCardLink && !routeIndex.has(activePath)) {
    activePath = normalizePath(fullCardLink.dataset.routePath);
  }
  updateRouteUI(routeIndex.get(activePath) || fullCardRoute);
})();