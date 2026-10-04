import { act, cleanup, fireEvent, render, screen } from "@testing-library/react";
import { useState } from "react";
import { afterEach, describe, expect, it, vi } from "vitest";
import type { SearchHit } from "../src/api/types";
import { PersonPicker, type Picked } from "../src/components/person/PersonPicker";

const endpoints = vi.hoisted(() => ({ searchPeople: vi.fn() }));
vi.mock("../src/api/endpoints", () => endpoints);

afterEach(() => {
  cleanup();
  vi.useRealTimers();
});

function Picker() {
  const [value, setValue] = useState<Picked | null>(null);
  return <PersonPicker label="Their name" value={value} onChange={setValue} />;
}

const hit = (name: string): SearchHit => ({ id: name.toLowerCase(), name, context: [] });

describe("person search", () => {
  it("keeps the last suggestions in view, not choosable, while the next search runs", async () => {
    vi.useFakeTimers();
    const answers: ((hits: SearchHit[]) => void)[] = [];
    endpoints.searchPeople.mockImplementation(
      () => new Promise((resolve) => answers.push((hits) => resolve({ results: hits }))),
    );
    render(<Picker />);
    const input = screen.getByRole("combobox");
    const answer = async (hits: SearchHit[]) => {
      await act(async () => vi.advanceTimersByTime(200));
      await act(async () => answers.at(-1)!(hits));
    };

    fireEvent.change(input, { target: { value: "Ra" } });
    await answer([hit("Ravi"), hit("Rani")]);
    expect(screen.getAllByRole("option").map((o) => o.textContent)).toEqual(["Ravi", "Rani", "+ Create a new person named “Ra”"]);

    fireEvent.change(input, { target: { value: "Ram" } });
    expect(screen.queryAllByRole("option")).toEqual([]);
    expect(screen.getByText("Ravi").closest("li")?.className).toBe("is-stale");
    expect(screen.getByText("Searching…")).toBeTruthy();
    fireEvent.keyDown(input, { key: "Enter" });
    expect(screen.queryByText(/Linking to/)).toBeNull();

    await answer([hit("Ramesh")]);
    expect(screen.queryByText("Ravi")).toBeNull();
    expect(screen.getAllByRole("option")[0].textContent).toBe("Ramesh");
  });
});
