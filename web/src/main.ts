import "./style.css";
import { type Dog, isImageUrl, renderBreeds, renderDogs } from "./render";

const grid = document.querySelector<HTMLElement>("#grid")!;
const select = document.querySelector<HTMLSelectElement>("#breed")!;
const status = document.querySelector<HTMLElement>("#status")!;

async function main() {
  const res = await fetch("/api/dogs");
  if (!res.ok) throw new Error(`API ${res.status}`);
  // Entries whose url is not https on the image host are dropped before rendering and counting.
  const dogs = ((await res.json()) as Dog[]).filter((d) => isImageUrl(d.url));
  renderBreeds(document, select, dogs);
  const show = (list: Dog[]) => renderDogs(document, grid, status, list);
  select.addEventListener("change", () => show(select.value ? dogs.filter((d) => d.breed === select.value) : dogs));
  show(dogs);
}

main().catch((e) => (status.textContent = `Could not load dogs: ${e.message}`));
