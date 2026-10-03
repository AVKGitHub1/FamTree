import { act, cleanup, fireEvent, render, screen, within } from "@testing-library/react";
import { useState } from "react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { ApiError } from "../src/api/client";
import type { AttributeDefinition, UploadedPicture } from "../src/api/types";
import { AttributeRows } from "../src/components/person/AttributeRows";
import { LOCATION, PROFILE_PIC } from "../src/lib/attributes";
import { rowsToPayload, type AttributeRow } from "../src/lib/attributeRows";

const endpoints = vi.hoisted(() => ({ uploadPicture: vi.fn(), pictureUrl: vi.fn() }));
vi.mock("../src/api/endpoints", () => endpoints);

const definitions = new Map<string, AttributeDefinition>([
  [PROFILE_PIC, { id: PROFILE_PIC, label: "Profile Pic", value_type: "image", builtin: true }],
  [LOCATION, { id: LOCATION, label: "Location", value_type: "text", builtin: true }],
]);
const OLD = "0123456789abcdef";

/** Uploads that finish when the test says so. */
function pendingUploads() {
  const uploads: { resolve: (picture: UploadedPicture) => void; reject: (error: unknown) => void }[] = [];
  endpoints.uploadPicture.mockImplementation(
    () => new Promise<UploadedPicture>((resolve, reject) => uploads.push({ resolve, reject })),
  );
  return uploads;
}

const uploaded = (id: string): UploadedPicture => ({ id, width: 10, height: 10, preview: `data:${id}` });

/** A public picture and a public location, edited as in the person panel. */
function renderForm() {
  let latest: AttributeRow[] = [];
  function Form() {
    const [rows, setRows] = useState<AttributeRow[]>(() => [
      { key: "pic", definition: { id: PROFILE_PIC }, draft: { type: "image", id: OLD, preview: "/old", uploading: false }, isPublic: true },
      { key: "loc", definition: { id: LOCATION }, draft: { type: "text", text: "Old location" }, isPublic: true },
    ]);
    latest = rows;
    return <AttributeRows rows={rows} definitions={definitions} onChange={setRows} />;
  }
  render(<Form />);
  return () => rowsToPayload(latest, definitions);
}

async function choosePicture() {
  const input = screen.getByLabelText(/(Choose|Replace) picture…/);
  await act(async () => {
    fireEvent.change(input, { target: { files: [new File(["x"], "new.jpg", { type: "image/jpeg" })] } });
  });
}

function editMeanwhile() {
  fireEvent.click(within(screen.getByRole("group", { name: "Profile Pic visibility" })).getByLabelText("🔒 Private"));
  fireEvent.change(screen.getByLabelText("Location"), { target: { value: "New location" } });
}

const settle = (step: () => void) =>
  act(async () => {
    step();
    await Promise.resolve();
  });

afterEach(() => {
  cleanup();
  vi.clearAllMocks();
});

describe("finishing a picture upload", () => {
  it("keeps the edits made while it was uploading", async () => {
    const uploads = pendingUploads();
    const payload = renderForm();
    await choosePicture();
    editMeanwhile();
    expect(payload().errors).toEqual(["Profile Pic: Wait until the picture has finished uploading."]);

    await settle(() => uploads[0].resolve(uploaded("fedcba9876543210")));
    expect(payload()).toEqual({
      attributes: [
        { definition: { id: PROFILE_PIC }, value: { id: "fedcba9876543210" }, is_public: false },
        { definition: { id: LOCATION }, value: "New location", is_public: true },
      ],
      definitions: [],
      errors: [],
    });
  });

  it("keeps them when the upload fails, along with the old picture", async () => {
    const uploads = pendingUploads();
    const payload = renderForm();
    await choosePicture();
    editMeanwhile();

    await settle(() => uploads[0].reject(new ApiError(422, "invalid", "That file is not a picture.")));
    expect(screen.getByRole("alert").textContent).toBe("That file is not a picture.");
    expect(payload().attributes).toEqual([
      { definition: { id: PROFILE_PIC }, value: { id: OLD }, is_public: false },
      { definition: { id: LOCATION }, value: "New location", is_public: true },
    ]);
  });

  it("does not bring back a picture removed meanwhile, nor replace a later upload", async () => {
    const uploads = pendingUploads();
    const payload = renderForm();
    await choosePicture();
    fireEvent.click(screen.getByRole("button", { name: "Remove Profile Pic" }));
    fireEvent.change(screen.getByLabelText("Add a detail"), { target: { value: PROFILE_PIC } });
    await choosePicture();

    await settle(() => uploads[0].resolve(uploaded("1111111111111111")));
    expect(screen.getAllByRole("group", { name: "Profile Pic" })).toHaveLength(1);
    expect(screen.getByText("Uploading…")).toBeTruthy();

    await settle(() => uploads[1].resolve(uploaded("2222222222222222")));
    expect(payload().attributes).toEqual([
      { definition: { id: LOCATION }, value: "Old location", is_public: true },
      { definition: { id: PROFILE_PIC }, value: { id: "2222222222222222" }, is_public: false },
    ]);
  });
});
