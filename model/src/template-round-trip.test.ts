import { describe, expect, it } from "vitest";
import { kind } from "@platforma-open/milaboratories.embedding-clustering.kind";
import { createPlDataTableStateV2 } from "@platforma-sdk/model";
import { initBlockData } from "./dataModel";
import { deriveTemplateParams } from "./templateParams";
import type { BlockData } from "./types";

/**
 * The three steps a project template actually takes between two blocks: the source block's
 * state is projected out, the file's params are read back by the kind, and the new block is
 * initialised from them. Anything one of the three drops is a setting the user has to make
 * again.
 */
const roundTrip = (data: BlockData): BlockData =>
  initBlockData(
    kind.parseInitializationParams(JSON.parse(JSON.stringify(deriveTemplateParams(data)))),
  );

/** Anchored keys, as `sequenceOptions` mints them and `deriveSourceSeqRefs` stores them. */
const ANCHORED_IDS = [
  '{"axes":[{"anchor":"main","idx":1}],"domain":{"pl7.app/alphabet":"aminoacid","pl7.app/vdj/feature":"CDR3"},"name":"pl7.app/vdj/sequence"}',
  '{"axes":[{"anchor":"main","idx":1}],"domain":{"pl7.app/alphabet":"aminoacid","pl7.app/vdj/feature":"FR4"},"name":"pl7.app/vdj/sequence"}',
] as BlockData["sequencesRef"];

const CONFIGURED: BlockData = {
  defaultBlockLabel: "ESM2 embedding, mcs:5",
  customBlockLabel: "run 7 clusters",
  datasetRef: { __isRef: true, blockId: "b1", name: "pf/dataset" },
  embeddingRef: { __isRef: true, blockId: "b2", name: "pf/embedding" },
  sequencesRef: ANCHORED_IDS,
  minClusterSize: 5,
  rescueNoise: false,
  mem: 128,
  cpu: 16,
  tableState: createPlDataTableStateV2(),
  graphStateBubble: { title: "x", template: "bubble", currentTab: null },
  alignmentModel: {},
  graphStateHistogram: { title: "y", template: "bins", currentTab: null },
};

describe("export -> apply", () => {
  it("carries every field a user set", () => {
    const seeded = roundTrip(CONFIGURED);

    expect(seeded.datasetRef).toEqual(CONFIGURED.datasetRef);
    expect(seeded.embeddingRef).toEqual(CONFIGURED.embeddingRef);
    expect(seeded.sequencesRef).toEqual(CONFIGURED.sequencesRef);
    expect(seeded.minClusterSize).toBe(CONFIGURED.minClusterSize);
    expect(seeded.rescueNoise).toBe(CONFIGURED.rescueNoise);
    expect(seeded.mem).toBe(CONFIGURED.mem);
    expect(seeded.cpu).toBe(CONFIGURED.cpu);
    expect(seeded.customBlockLabel).toBe(CONFIGURED.customBlockLabel);
  });

  it("is stable: seeding from the seeded block changes nothing", () => {
    const once = roundTrip(CONFIGURED);
    expect(roundTrip(once)).toEqual(once);
  });

  it("survives a half-configured block, which the panel reaches and the projection must return", () => {
    const half: BlockData = {
      ...CONFIGURED,
      embeddingRef: undefined,
      sequencesRef: [],
      customBlockLabel: "",
      mem: undefined,
      cpu: undefined,
    };
    const seeded = roundTrip(half);

    expect(seeded.datasetRef).toEqual(half.datasetRef);
    expect(seeded.embeddingRef).toBeUndefined();
    expect(seeded.sequencesRef).toEqual([]);
    expect(seeded.mem).toBeUndefined();
    expect(seeded.cpu).toBeUndefined();
  });

  it("seeds a block with no params at all from the defaults", () => {
    const fresh = initBlockData(undefined);

    expect(fresh.minClusterSize).toBe(2);
    expect(fresh.rescueNoise).toBe(true);
    expect(fresh.sequencesRef).toEqual([]);
    expect(fresh.customBlockLabel).toBe("");
    expect(fresh.datasetRef).toBeUndefined();
  });

  it("leaves the derived label to the panel, and agrees with it on the part it can compute", () => {
    // The watchEffect in ui/src/app.ts builds the same string from the resolved cluster size
    // and the embedding column's option label. `init` cannot reach the option label -- it comes
    // from the result pool -- so the placeholder stands until the panel resolves it, but the
    // cluster size must already match or the block would re-run the moment it was opened.
    const seeded = roundTrip(CONFIGURED);

    expect(seeded.defaultBlockLabel).not.toBe(CONFIGURED.defaultBlockLabel);
    expect(seeded.defaultBlockLabel).toContain(`mcs:${CONFIGURED.minClusterSize}`);
  });

  it("resets the view state rather than carrying it", () => {
    const seeded = roundTrip(CONFIGURED);

    expect(seeded.alignmentModel).toEqual({});
    expect(seeded.graphStateBubble.template).toBe("bubble");
    expect(seeded.graphStateHistogram.template).toBe("bins");
  });
});
