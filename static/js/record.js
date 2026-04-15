(function () {
  const dataNode = document.getElementById('record-page-data');
  if (!dataNode) return;

  let pageData = {};
  try {
    pageData = JSON.parse(dataNode.textContent || '{}');
  } catch (error) {
    console.error('Failed to parse record page data', error);
    return;
  }

  const body = document.body;
  const routeLinks = Array.from(document.querySelectorAll('[data-route-link][data-route-path]'));
  const routeRows = Array.from(document.querySelectorAll('.rec-summary-row[data-route-path]'));
  const mobileLinks = Array.from(document.querySelectorAll('.mobile-record-link[data-route-path]'));
  const panels = Array.from(document.querySelectorAll('.recap-panel[data-selected-key]'));
  const emptyState = document.getElementById('record-empty-state');
  const heroSubtitle = document.getElementById('record-hero-subtitle');
  const viewChip = document.getElementById('record-view-chip');
  const panelShell = document.getElementById('recap-panel-shell');

  const normalizePath = (path) => (path && path !== '/' ? path.replace(/\/+$/, '') : path || '/');
  const routeIndex = new Map();
  const indexRoute = pageData.index || {};
  routeIndex.set(normalizePath(indexRoute.path), indexRoute);
  Object.values(pageData.recaps || {}).forEach((route) => routeIndex.set(normalizePath(route.path), route));

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
    selectedKey: route.selected_key || null,
    trackName: route.trackName || null,
    raceDate: route.raceDate || null,
    dailyScore: route.dailyScore || null,
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
    body.dataset.selectedKey = detail.selectedKey || '';
    document.title = detail.title;
    setAttr('#meta-description', 'content', detail.description);
    setAttr('#canonical-link', 'href', detail.absoluteUrl);
    setAttr('#og-type', 'content', detail.viewMode === 'recap' ? 'article' : 'website');
    setAttr('#og-title', 'content', detail.title);
    setAttr('#og-description', 'content', detail.description);
    setAttr('#og-url', 'content', detail.absoluteUrl);
    setAttr('#twitter-title', 'content', detail.title);
    setAttr('#twitter-description', 'content', detail.description);

    if (heroSubtitle) {
      heroSubtitle.textContent = detail.viewMode === 'recap' && detail.trackName && detail.raceDate
        ? `Focused recap review for ${detail.trackName} on ${detail.raceDate}.`
        : 'Verified outcomes, disciplined review, and transparent public performance tracking across official Equibase results.';
    }
    if (viewChip) {
      viewChip.textContent = detail.viewMode === 'recap' && detail.trackName
        ? `🧾 ${detail.trackName} Recap`
        : '📊 30-Day Summary';
    }

    routeLinks.forEach((link) => {
      const isActive = normalizePath(link.dataset.routePath) === normalizePath(detail.path);
      link.classList.toggle('is-active', isActive);
      if (isActive) link.setAttribute('aria-current', 'page');
      else link.removeAttribute('aria-current');
    });

    [...routeRows, ...mobileLinks].forEach((node) => {
      const isSelected = detail.selectedKey && node.dataset.selectedKey === detail.selectedKey;
      node.classList.toggle('is-active', Boolean(isSelected));
      if (isSelected) node.setAttribute('aria-current', 'page');
      else node.removeAttribute('aria-current');
    });

    if (emptyState) emptyState.classList.toggle('is-active', detail.viewMode === 'summary');
    panels.forEach((panel) => panel.classList.toggle('is-active', detail.selectedKey && panel.dataset.selectedKey === detail.selectedKey));
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
      if (route.view_mode === 'recap' && route.selected_key) {
        const activePanel = document.querySelector(`.recap-panel[data-selected-key="${route.selected_key}"]`);
        activePanel?.scrollIntoView({ behavior: 'smooth', block: 'start' });
      } else {
        panelShell?.scrollIntoView({ behavior: 'smooth', block: 'start' });
      }
    }
    activePath = nextPath;
  };

  document.addEventListener('click', (event) => {
    const trigger = event.target.closest('[data-route-link][data-route-path]');
    if (!trigger || event.defaultPrevented || event.metaKey || event.ctrlKey || event.shiftKey || event.altKey) return;
    const route = routeIndex.get(normalizePath(trigger.dataset.routePath));
    if (!route) return;
    event.preventDefault();
    applyRoute(route, { push: true, track: true, scroll: true });
  });

  routeRows.forEach((row) => {
    row.addEventListener('keydown', (event) => {
      if (event.key !== 'Enter' && event.key !== ' ') return;
      const route = routeIndex.get(normalizePath(row.dataset.routePath));
      if (!route) return;
      event.preventDefault();
      applyRoute(route, { push: true, track: true, scroll: true });
    });
  });

  window.addEventListener('popstate', () => {
    const route = routeIndex.get(normalizePath(window.location.pathname));
    if (route) applyRoute(route, { push: false, track: true, scroll: false });
  });

  updateRouteUI(routeIndex.get(activePath) || indexRoute);
})();