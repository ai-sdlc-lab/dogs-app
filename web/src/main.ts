import "./style.css";

type Dog = { breed: string; url: string };

const grid = document.querySelector<HTMLElement>("#grid")!;
const select = document.querySelector<HTMLSelectElement>("#breed")!;
const status = document.querySelector<HTMLElement>("#status")!;

// DOM APIs only (no innerHTML): API data is never parsed as markup.
function render(dogs: Dog[]) {
  grid.replaceChildren(
    ...dogs.map((d) => {
      const fig = document.createElement("figure");
      const img = document.createElement("img");
      img.src = d.url;
      img.alt = d.breed;
      img.loading = "lazy";
      const cap = document.createElement("figcaption");
      cap.textContent = d.breed;
      fig.append(img, cap);
      return fig;
    }),
  );
  status.textContent = `${dogs.length} dog${dogs.length === 1 ? "" : "s"}`;
}

async function main() {
  const res = await fetch("/api/dogs");
  if (!res.ok) throw new Error(`API ${res.status}`);
  const dogs: Dog[] = await res.json();
  for (const breed of [...new Set(dogs.map((d) => d.breed))].sort()) {
    select.add(new Option(breed, breed));
  }
  select.addEventListener("change", () =>
    render(select.value ? dogs.filter((d) => d.breed === select.value) : dogs),
  );
  render(dogs);
}

main().catch((e) => (status.textContent = `Could not load dogs: ${e.message}`));
