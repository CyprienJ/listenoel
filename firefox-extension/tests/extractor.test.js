const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const test = require("node:test");
const vm = require("node:vm");

const extractor = fs.readFileSync(path.join(__dirname, "..", "extractor.js"), "utf8");

function element({ text = "", value = "", href = "", src = "", width = 800, height = 800 } = {}) {
  return {
    textContent: text,
    value,
    href,
    src,
    currentSrc: src,
    naturalWidth: width,
    naturalHeight: height,
    content: "",
    getAttribute(name) {
      return name === "aria-label" ? "" : null;
    },
    getBoundingClientRect() {
      return { width, height };
    }
  };
}

function extractFixture(fixture) {
  const title = element({ text: fixture.title });
  const price = element({ text: fixture.price });
  const image = element({ src: fixture.image });
  const action = element({ text: fixture.action, value: fixture.action });
  const canonical = element({ href: fixture.url });

  const document = {
    baseURI: fixture.url,
    title: `${fixture.title} | Shop`,
    querySelector(selector) {
      if (selector.includes('meta[property=')) return null;
      if (selector.includes('itemtype*="schema.org/Product"')) return null;
      if (selector === "#productTitle") return fixture.merchant === "amazon" ? title : null;
      if (selector === "#landingImage, #imgBlkFront") return fixture.merchant === "amazon" ? image : null;
      if (selector === '.a-price:not(.a-text-price) .a-offscreen') {
        return fixture.merchant === "amazon" ? price : null;
      }
      if (selector.includes('.f-priceBox-price')) return fixture.merchant === "fnac" ? price : null;
      if (selector === 'link[rel="canonical"]') return canonical;
      if (selector === "main h1, h1") return title;
      if (selector.includes('[itemprop="sku"]')) return element({ text: fixture.identifier });
      return null;
    },
    querySelectorAll(selector) {
      if (selector === 'script[type="application/ld+json"]') return [];
      if (selector.includes('[class*="price" i]')) return [price];
      if (selector.includes('main img')) return [image];
      if (selector.startsWith("button,")) return [action];
      return [];
    }
  };

  return vm.runInNewContext(extractor, {
    URL,
    document,
    location: { href: fixture.url },
    getComputedStyle: () => ({ display: "block", visibility: "visible" })
  });
}

test("extracts a Fnac product", () => {
  const fnac = extractFixture({
    merchant: "fnac",
    url: "https://www.fnac.com/a23085276/Grand-Theft-Auto-GTA-VI-PS5-Jeu-video-Playstation-5",
    title: "Grand Theft Auto GTA VI PS5",
    price: "79,99 €",
    image: "https://static.fnac-static.com/gta-vi.jpg",
    action: "Précommander",
    identifier: "9340370"
  });

  assert.equal(fnac.detection.isProduct, true);
  assert.equal(fnac.title, "Grand Theft Auto GTA VI PS5");
  assert.equal(fnac.price, "79.99");
  assert.ok(fnac.detection.signals.includes("purchase action"));
});

test("extracts an Amazon product and removes attribution parameters", () => {
  const amazon = extractFixture({
    merchant: "amazon",
    url: "https://www.amazon.fr/KLARSTEIN-DryFy-Connect/deshumidificateur/dp/B08HRWNHNV/?_encoding=UTF8&pd_rd_w=LM9iQ&content-id=amzn1.sym.test&pf_rd_p=8108b942&th=1",
    title: "KLARSTEIN DryFy Connect Déshumidificateur",
    price: "189,99 €",
    image: "https://m.media-amazon.com/images/dryfy.jpg",
    action: "Ajouter au panier",
    identifier: "B08HRWNHNV"
  });

  assert.equal(amazon.detection.isProduct, true);
  assert.equal(amazon.title, "KLARSTEIN DryFy Connect Déshumidificateur");
  assert.equal(amazon.price, "189.99");
  assert.equal(
    amazon.url,
    "https://www.amazon.fr/KLARSTEIN-DryFy-Connect/deshumidificateur/dp/B08HRWNHNV/"
  );
  assert.ok(amazon.detection.signals.includes("purchase action"));
});

test("does not classify an article as a product", () => {
  const article = extractFixture({
    merchant: "news",
    url: "https://example.com/articles/gta-vi-release-date",
    title: "Everything we know about GTA VI",
    price: "",
    image: "https://example.com/gta-vi.jpg",
    action: "Read more",
    identifier: ""
  });

  assert.equal(article.detection.isProduct, false);
});
