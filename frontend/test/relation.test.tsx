import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";
import type { RelationOutcome, RelationResult } from "../src/api/types";
import { RelationResults } from "../src/components/relation/RelationFlow";

afterEach(cleanup);

function result(statement: string, marathi: string[]): RelationResult {
  return {
    kind: "cousin",
    label: "first cousin",
    statement,
    marathi,
    distance_a: 2,
    distance_b: 2,
    cousin_degree: 1,
    removed: 0,
    common_ancestors: [],
    path: [],
  };
}

function show(outcome: RelationOutcome) {
  const noop = () => {};
  render(<RelationResults outcome={outcome} error={null} active={0} onActivate={noop} onAgain={noop} onClose={noop} onSwap={noop} />);
}

describe("Marathi relationship names", () => {
  it("shows each result's Marathi name only after the button is pressed", () => {
    show({
      a: "a",
      b: "b",
      message: null,
      results: [result("Asha is Ravi’s grandmother.", ["आजी", "आईकडची आजी"]), result("Asha is Ravi’s spouse.", [])],
    });
    expect(screen.queryByText("आजी")).toBeNull();
    const button = screen.getByRole("button", { name: "मराठीत नातं" });
    fireEvent.click(button);
    expect(button.getAttribute("aria-pressed")).toBe("true");
    expect(screen.getByText("आजी").getAttribute("lang")).toBe("mr");
    expect(screen.getByText("आईकडची आजी")).toBeTruthy();
    expect(screen.getByText("No Marathi relationship name found.")).toBeTruthy();
    fireEvent.click(button);
    expect(screen.queryByText("आजी")).toBeNull();
  });

  it("has no Marathi button when no relationship was found", () => {
    show({ a: "a", b: "b", message: "No relationship found in the available data.", results: [] });
    expect(screen.queryByRole("button", { name: "मराठीत नातं" })).toBeNull();
  });
});
