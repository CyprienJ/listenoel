try {
globalThis.__NOSCADEAUX_PRODUCT__ = (() => {
  const candidates = { titles: [], urls: [], images: [], prices: [] };
  const detectionSignals = new Set();
  const PRODUCT_ACTION_PATTERNS = [
    /\bajouter au panier\b/i,
    /\bajouter dans le panier\b/i,
    /\b(?:acheter|commander|precommander|reserver)\b/i,
    /\badd to (?:cart|bag|basket)\b/i,
    /\b(?:buy now|order now|pre-?order)\b/i
  ];

  const cleanText = (value) => String(value || "").replace(/\s+/g, " ").trim();
  const absoluteHttpUrl = (value) => {
    if (!value) return null;
    try {
      const url = new URL(value, document.baseURI);
      return ["http:", "https:"].includes(url.protocol) ? url.href : null;
    } catch {
      return null;
    }
  };
  const add = (bucket, value, source, confidence, extra = {}) => {
    value = cleanText(value);
    if (!value) return;
    bucket.push({ value, source, confidence, ...extra });
  };
  const meta = (name) =>
    document.querySelector(`meta[property="${name}"], meta[name="${name}"]`)?.content;

  function jsonLdNodes(value) {
    if (!value || typeof value !== "object") return [];
    if (Array.isArray(value)) return value.flatMap(jsonLdNodes);
    const nodes = [value];
    if (value["@graph"]) nodes.push(...jsonLdNodes(value["@graph"]));
    return nodes;
  }

  function isProduct(node) {
    const types = Array.isArray(node?.["@type"]) ? node["@type"] : [node?.["@type"]];
    return types.some((type) => String(type).toLowerCase() === "product");
  }

  function imagesFrom(value) {
    if (Array.isArray(value)) return value.flatMap(imagesFrom);
    if (value && typeof value === "object") return imagesFrom(value.url || value.contentUrl);
    const url = absoluteHttpUrl(value);
    return url ? [url] : [];
  }

  function offersFrom(value) {
    if (!value) return [];
    if (Array.isArray(value)) return value.flatMap(offersFrom);
    if (value.offers) return offersFrom(value.offers);
    return [value];
  }

  function extractJsonLd() {
    for (const script of document.querySelectorAll('script[type="application/ld+json"]')) {
      try {
        const products = jsonLdNodes(JSON.parse(script.textContent)).filter(isProduct);
        for (const product of products) addJsonLdProduct(product);
      } catch {
        // Broken JSON-LD is common; lower-priority sources still apply.
      }
    }
  }

  function addJsonLdProduct(product) {
    detectionSignals.add("json-ld:Product");
    add(candidates.titles, product.name, "json-ld", 1);
    add(candidates.urls, absoluteHttpUrl(product.url), "json-ld", 0.98);
    for (const image of imagesFrom(product.image)) {
      add(candidates.images, image, "json-ld", 0.98);
    }
    for (const offer of offersFrom(product.offers)) {
      const price = offer.price ?? offer.lowPrice ?? offer.priceSpecification?.price;
      const currency = offer.priceCurrency ?? offer.priceSpecification?.priceCurrency;
      const parsed = normalizeAmount(price);
      if (parsed) add(candidates.prices, parsed, "json-ld", 1, { currency: currency || null });
    }
  }

  function extractMetadata() {
    add(candidates.titles, meta("og:title"), "open-graph", 0.9);
    add(candidates.urls, absoluteHttpUrl(meta("og:url")), "open-graph", 0.9);
    add(candidates.images, absoluteHttpUrl(meta("og:image")), "open-graph", 0.9);
    const metaPrice = normalizeAmount(meta("product:price:amount"));
    if (metaPrice) {
      detectionSignals.add("product-price metadata");
      add(candidates.prices, metaPrice, "open-graph", 0.9, {
        currency: meta("product:price:currency") || null
      });
    }
    if (/product/i.test(meta("og:type") || "")) detectionSignals.add("og:type product");
    if (document.querySelector('[itemtype*="schema.org/Product" i], [itemtype$="/Product" i]')) {
      detectionSignals.add("Product microdata");
    }
  }

  function extractMerchantData() {
    add(candidates.titles, document.querySelector("#productTitle")?.textContent, "amazon-product-title", 0.99);
    const amazonImage = document.querySelector("#landingImage, #imgBlkFront");
    add(
      candidates.images,
      absoluteHttpUrl(amazonImage?.currentSrc || amazonImage?.src),
      "amazon-product-image",
      0.99
    );
    addPriceElement(
      document.querySelector('.a-price:not(.a-text-price) .a-offscreen'),
      "amazon-product-price",
      0.98
    );
    addPriceElement(
      document.querySelector('.f-priceBox-price, [class*="userPrice" i], [data-automation-id="product-price"]'),
      "fnac-product-price",
      0.96
    );
  }

  function addPriceElement(element, source, confidence) {
    const price = normalizeAmount(element?.textContent);
    if (price) {
      add(candidates.prices, price, source, confidence, { currency: currencyFrom(element.textContent) });
    }
  }

  function extractPageData() {
    add(candidates.titles, document.querySelector('[itemprop="name"]')?.textContent, "microdata", 0.85);
    add(candidates.urls, absoluteHttpUrl(document.querySelector('link[rel="canonical"]')?.href), "canonical", 0.95);
    add(candidates.titles, document.querySelector("main h1, h1")?.textContent, "heading", 0.75);
    add(candidates.titles, documentTitle(), "document-title", 0.5);
    addMicrodataPrice();
    addVisiblePrices();
    addVisibleImages();
  }

  function documentTitle() {
    const separators = [" | ", " – ", " — ", " - "];
    const separatorIndex = Math.max(...separators.map((separator) => document.title.lastIndexOf(separator)));
    return separatorIndex < 0 ? document.title : document.title.slice(0, separatorIndex);
  }

  function addMicrodataPrice() {
    const priceElement = document.querySelector('[itemprop="price"]');
    const price = normalizeAmount(priceElement?.content || priceElement?.textContent);
    if (!price) return;
    const currencyElement = document.querySelector('[itemprop="priceCurrency"]');
    add(candidates.prices, price, "microdata", 0.85, {
      currency: currencyElement?.content || currencyElement?.textContent || null
    });
  }

  function addVisiblePrices() {
    const elements = document.querySelectorAll('[class*="price" i], [id*="price" i], [data-testid*="price" i]');
    for (const element of [...elements].slice(0, 100)) {
      if (!isVisible(element)) continue;
      const text = cleanText(element.textContent);
      const amount = normalizeAmount(text);
      if (amount) add(candidates.prices, amount, "page", 0.45, { currency: currencyFrom(text) });
    }
  }

  function addVisibleImages() {
    const images = document.querySelectorAll('main img, [class*="product" i] img, [class*="gallery" i] img');
    for (const image of [...images].slice(0, 80)) {
      if (!isVisible(image)) continue;
      const url = absoluteHttpUrl(image.currentSrc || image.src);
      if (!url || image.naturalWidth < 200 || image.naturalHeight < 200) continue;
      const area = Math.min(image.naturalWidth * image.naturalHeight, 4000000);
      add(candidates.images, url, "page-image", 0.4 + area / 10000000);
    }
  }

  extractJsonLd();
  extractMetadata();
  extractMerchantData();
  extractPageData();

  for (const key of Object.keys(candidates)) {
    candidates[key] = deduplicate(candidates[key]).sort((a, b) => b.confidence - a.confidence);
  }

  const selectedPrice = candidates.prices[0] || null;
  const selectedUrl = cleanProductUrl(candidates.urls[0]?.value || location.href);
  const detection = detectProductPage(selectedUrl);
  return {
    title: candidates.titles[0]?.value || "",
    url: selectedUrl,
    imageUrl: candidates.images[0]?.value || "",
    price: selectedPrice?.value || "",
    currency: cleanText(selectedPrice?.currency).toUpperCase() || currencyFrom(selectedPrice?.value) || "EUR",
    candidates,
    detection
  };

  function detectProductPage(url) {
    const normalizedActions = [...document.querySelectorAll(
      'button, [role="button"], input[type="submit"], input[type="button"], a[href*="cart" i], a[href*="panier" i]'
    )]
      .slice(0, 500)
      .map((element) => normalizeForMatch(element.value || element.getAttribute("aria-label") || element.textContent))
      .filter(hasProductAction);

    if (normalizedActions.length) detectionSignals.add("purchase action");
    if (candidates.prices.length) detectionSignals.add("price");
    if (candidates.titles.some((item) => item.source !== "document-title")) detectionSignals.add("product heading");
    if (candidates.images.length) detectionSignals.add("product image");

    const productUrl = isProductUrl(new URL(url).pathname);
    if (productUrl) detectionSignals.add("product URL");

    const productIdentifier = Boolean(
      document.querySelector(
        '[itemprop="sku"], [itemprop="gtin"], [itemprop="gtin13"], #ASIN, input[name="ASIN"], [data-product-id]'
      )
    );
    if (productIdentifier) detectionSignals.add("product identifier");

    const structuredProduct = ["json-ld:Product", "og:type product", "Product microdata"]
      .some((signal) => detectionSignals.has(signal));
    const hasPrice = candidates.prices.length > 0;
    const hasTitle = candidates.titles.some((item) => item.source !== "document-title");
    const hasImage = candidates.images.length > 0;
    const hasAction = normalizedActions.length > 0;

    const heuristicProduct =
      (productUrl && (hasPrice || hasAction || productIdentifier)) ||
      (hasPrice && hasAction && hasTitle && hasImage && normalizedActions.length <= 6);

    const score = Math.min(
      100,
      (structuredProduct ? 100 : 0) +
        (productUrl ? 35 : 0) +
        (hasPrice ? 25 : 0) +
        (hasAction ? 25 : 0) +
        (productIdentifier ? 20 : 0) +
        (hasTitle ? 10 : 0) +
        (hasImage ? 10 : 0)
    );

    return {
      isProduct: structuredProduct || heuristicProduct,
      score,
      signals: [...detectionSignals]
    };
  }

  function normalizeForMatch(value) {
    return cleanText(value)
      .normalize("NFD")
      .replace(/\p{M}/gu, "")
      .toLowerCase();
  }

  function hasProductAction(text) {
    return PRODUCT_ACTION_PATTERNS.some((pattern) => pattern.test(text));
  }

  function isProductUrl(path) {
    return (
      /\/dp\/[A-Z0-9]{10}(?:\/|$)/i.test(path) ||
      /\/a\d+(?:\/|$)/i.test(path) ||
      /\/products?\/[^/]+/i.test(path) ||
      /\/item\/[^/]+/i.test(path)
    );
  }

  function isVisible(element) {
    const style = getComputedStyle(element);
    const rect = element.getBoundingClientRect();
    return style.display !== "none" && style.visibility !== "hidden" && rect.width > 0 && rect.height > 0;
  }

  function normalizeAmount(value) {
    const text = cleanText(value);
    const match = /(?:\d{1,3}(?:[\s.,']\d{3})+|\d+)(?:[.,]\d{1,2})?/.exec(text);
    if (!match) return null;
    let amount = match[0].replaceAll(" ", "").replaceAll("'", "");
    const comma = amount.lastIndexOf(",");
    const dot = amount.lastIndexOf(".");
    if (comma >= 0 && dot >= 0) {
      const decimal = Math.max(comma, dot);
      amount = amount.slice(0, decimal).replaceAll(".", "").replaceAll(",", "") + "." + amount.slice(decimal + 1);
    } else if (comma >= 0) {
      const decimals = amount.length - comma - 1;
      amount = decimals <= 2 ? amount.replaceAll(".", "").replaceAll(",", ".") : amount.replaceAll(",", "");
    } else if (dot >= 0) {
      const decimals = amount.length - dot - 1;
      if (decimals === 3) amount = amount.replaceAll(".", "");
    }
    const number = Number(amount);
    return Number.isFinite(number) && number >= 0 ? number.toFixed(2) : null;
  }

  function currencyFrom(value) {
    const text = cleanText(value).toUpperCase();
    if (/€|\bEUR\b/.test(text)) return "EUR";
    if (/£|\bGBP\b/.test(text)) return "GBP";
    if (/¥|\bJPY\b/.test(text)) return "JPY";
    if (/\$|\bUSD\b/.test(text)) return "USD";
    return null;
  }

  function deduplicate(values) {
    const seen = new Set();
    return values.filter((item) => {
      const key = `${item.value}|${item.currency || ""}`.toLowerCase();
      if (seen.has(key)) return false;
      seen.add(key);
      return true;
    });
  }

  function cleanProductUrl(value) {
    const url = new URL(value, location.href);
    url.hash = "";

    // Amazon product paths contain the stable ASIN; their query string is attribution
    // and recommendation context rather than product identity.
    if (/(^|\.)amazon\.[a-z.]+$/i.test(url.hostname) && /\/dp\/[A-Z0-9]{10}(?:[/?]|$)/i.test(url.pathname)) {
      url.search = "";
      return url.href;
    }

    // Avoid URLSearchParams iteration here. Firefox page compartments can expose
    // an iterator whose `next` method rejects the wrapped receiver.
    const keptParameters = url.search
      .slice(1)
      .split("&")
      .filter(Boolean)
      .filter((parameter) => {
        const encodedKey = parameter.split("=", 1)[0];
        let key = encodedKey;
        try {
          key = decodeURIComponent(encodedKey.replaceAll("+", " "));
        } catch {
          // Keep malformed parameters rather than breaking product extraction.
        }
        return !/^(utm_.+|fbclid|gclid|mc_cid|mc_eid)$/i.test(key);
      });
    url.search = keptParameters.length ? `?${keptParameters.join("&")}` : "";
    return url.href;
  }

})();
} catch (error) {
  globalThis.__NOSCADEAUX_PRODUCT__ = {
    extractionError: error?.stack || error?.message || String(error)
  };
}
({ ...globalThis.__NOSCADEAUX_PRODUCT__ });
