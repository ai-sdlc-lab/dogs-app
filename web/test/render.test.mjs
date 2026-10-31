// SR-003 frontend tests (change 0002). Built-in node:test only; Node strips the types of render.ts.
// Inside describe() so the JUnit report has a <testsuite> for security.yml's merge step.
import assert from "node:assert/strict";
import { describe, test } from "node:test";
import { renderBreeds, renderDogs } from "../src/render.ts";

const HOST = "sdlc-lab-app-dogs-dev-992382408037.s3.eu-north-1.amazonaws.com";
const GOOD = `https://${HOST}/dogs/pug/1.jpg?X-Amz-Signature=abc`;

// Minimal fake DOM: it never parses markup, it only records which elements the code creates.
function fakeDocument() {
  const created = [];
  const element = (tag) => ({
    tagName: tag.toUpperCase(),
    children: [],
    textContent: "",
    append(...nodes) {
      this.children.push(...nodes);
    },
    replaceChildren(...nodes) {
      this.children = nodes;
    },
  });
  const doc = {
    created,
    createElement(tag) {
      const el = element(tag);
      created.push(el);
      return el;
    },
  };
  return { doc, grid: element("main"), status: element("p"), select: element("select") };
}

const tags = (els) => els.map((e) => e.tagName);

describe("render", () => {
  test("test_breed_with_script_renders_as_text", () => {
    const { doc, grid, status, select } = fakeDocument();
    const breed = "<script>alert(1)</script>";
    const url = `https://${HOST}/dogs/pug/<img src=x onerror=alert(1)>.jpg?X-Amz-Signature=abc`;
    const dogs = [{ breed, url }];
    renderBreeds(doc, select, dogs);
    renderDogs(doc, grid, status, dogs);

    assert.deepEqual(tags(doc.created).sort(), ["FIGCAPTION", "FIGURE", "IMG", "OPTION"]);
    const [fig] = grid.children;
    const [img, cap] = fig.children;
    assert.equal(img.src, url);
    assert.equal(img.alt, breed);
    assert.equal(cap.textContent, breed);
    assert.equal(select.children[0].textContent, breed);
    assert.equal(select.children[0].value, breed);
    assert.equal(status.textContent, "1 dog");
  });

  test("test_frontend_rejects_non_https_or_foreign_image_urls", () => {
    const { doc, grid, status } = fakeDocument();
    const bad = [
      `http://${HOST}/dogs/pug/1.jpg`,
      "javascript:alert(1)",
      "data:image/png;base64,AAAA",
      `//${HOST}/dogs/pug/1.jpg`,
      `https://user:pass@${HOST}/dogs/pug/1.jpg`,
      `https://${HOST}:8443/dogs/pug/1.jpg`,
      "https://evil.example/dogs/pug/1.jpg",
      "https://sdlc-lab-app-dogs-dev-992382408037.s3.us-east-1.amazonaws.com/dogs/pug/1.jpg",
      "/dogs/pug/1.jpg",
    ];
    renderDogs(doc, grid, status, [...bad.map((url) => ({ breed: "pug", url })), { breed: "pug", url: GOOD }]);

    assert.equal(grid.children.length, 1);
    assert.equal(grid.children[0].children[0].src, GOOD);
    assert.equal(status.textContent, "1 dog");
  });
});
