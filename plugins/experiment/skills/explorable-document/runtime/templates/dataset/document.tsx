import { useState } from "react";

const rows = [
  { id: "alpha", name: "Alpha", count: 12 },
  { id: "beta", name: "Beta", count: 5 },
  { id: "gamma", name: "Gamma", count: 9 },
];
export default function Dataset() {
  const [filter, setFilter] = useState("");
  const [ascending, setAscending] = useState(true);
  const [selected, setSelected] = useState<string | null>(null);
  const shown = rows
    .filter((row) => row.name.toLowerCase().includes(filter.toLowerCase()))
    .sort((a, b) => (ascending ? a.count - b.count : b.count - a.count));
  const current = shown.find((row) => row.id === selected);
  function changeFilter(value: string) {
    setFilter(value);
    setSelected(null);
  }
  return (
    <>
      <h1>A small dataset, connected views</h1>
      <p>
        These three synthetic records have counts, not measurements from a live
        service.
      </p>
      <label htmlFor="filter">Filter by name</label>
      <input
        id="filter"
        type="text"
        value={filter}
        onChange={(e) => changeFilter(e.target.value)}
      />
      <p>
        <button type="button" onClick={() => setAscending(!ascending)}>
          Sort {ascending ? "descending" : "ascending"}
        </button>
      </p>
      <div id="records">
        {shown.length ? (
          <table>
            <caption>Synthetic counts</caption>
            <thead>
              <tr>
                <th>Name</th>
                <th>Count</th>
                <th>Details</th>
              </tr>
            </thead>
            <tbody>
              {shown.map((row) => (
                <tr key={row.id}>
                  <td>{row.name}</td>
                  <td>{row.count}</td>
                  <td>
                    <button
                      type="button"
                      aria-pressed={row.id === selected}
                      onClick={() => setSelected(row.id)}
                    >
                      Select {row.name}
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        ) : (
          <p>No matching records.</p>
        )}
      </div>
      <p id="selection" aria-live="polite">
        {current
          ? `${current.name}: ${current.count} items.`
          : "No record selected."}
      </p>
    </>
  );
}
