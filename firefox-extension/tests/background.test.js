const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const test = require("node:test");
const vm = require("node:vm");

const background = fs.readFileSync(path.join(__dirname, "..", "background.js"), "utf8");

function loadBackground({ executeScript, requestPermission } = {}) {
  const storageWrites = [];
  const browser = {
    action: { onClicked: { addListener() {} } },
    runtime: { onMessage: { addListener() {} } },
    scripting: {
      executeScript: executeScript || (async () => [])
    },
    sidebarAction: { open: async () => undefined },
    storage: {
      session: {
        async set(value) {
          storageWrites.push(value);
        }
      }
    },
    permissions: {
      request: requestPermission || (async () => true)
    }
  };
  const context = vm.createContext({ browser, URL });
  vm.runInContext(background, context);
  const functions = vm.runInContext("({ requestTabPermission, scanTab, friendlyError })", context);
  return { ...functions, storageWrites };
}

test("requests access only for the active shop origin", async () => {
  let requestedOrigins;
  const { requestTabPermission } = loadBackground({
    requestPermission: async ({ origins }) => {
      requestedOrigins = origins;
      return true;
    }
  });

  assert.equal(await requestTabPermission("https://shop.example:8443/products/42?ref=home"), true);
  assert.equal(requestedOrigins.length, 1);
  assert.equal(requestedOrigins[0], "https://shop.example/*");
});

test("rejects browser pages without asking for permission", async () => {
  let permissionRequested = false;
  const { requestTabPermission } = loadBackground({
    requestPermission: async () => {
      permissionRequested = true;
      return true;
    }
  });

  await assert.rejects(requestTabPermission("about:config"), /cannot be scanned/);
  assert.equal(permissionRequested, false);
});

test("stores a ready capture after a successful scan", async () => {
  const product = {
    title: "Desk lamp",
    url: "https://shop.example/products/lamp",
    detection: { isProduct: true }
  };
  const { scanTab, storageWrites } = loadBackground({
    executeScript: async () => [{ frameId: 0, result: product }]
  });

  const result = await scanTab({ id: 12 }, "capture:7");

  assert.equal(result.ok, true);
  assert.equal(storageWrites.length, 2);
  assert.equal(storageWrites[0]["capture:7"].status, "loading");
  assert.equal(storageWrites[1]["capture:7"].status, "ready");
  assert.equal(storageWrites[1]["capture:7"].product, product);
});

test("stores a useful error when extraction does not find a product", async () => {
  const { scanTab, storageWrites } = loadBackground({
    executeScript: async () => [{ frameId: 0, result: { title: "Article", url: "https://example.com/article" } }]
  });

  const result = await scanTab({ id: 12 }, "capture:7");

  assert.equal(result.ok, false);
  assert.match(result.error, /does not appear to be a product/);
  assert.equal(storageWrites.at(-1)["capture:7"].status, "error");
  assert.match(storageWrites.at(-1)["capture:7"].message, /does not appear to be a product/);
});

test("turns Firefox permission errors into actionable messages", () => {
  const { friendlyError } = loadBackground();
  const message = friendlyError(new Error("Missing host permission for the tab"));

  assert.match(message, /Firefox blocked access/);
  assert.match(message, /click the Quick Add toolbar button again/i);
});
