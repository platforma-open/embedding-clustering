import { describe, expect, it } from "vitest";
import { kind } from "./index";

const parse = (params: unknown) => kind.parseInitializationParams(params);

const REF = { __isRef: true as const, blockId: "b1", name: "pf/dataset" };

/**
 * The shape the `sequenceOptions` output mints, which is what the panel's
 * `deriveSourceSeqRefs` writes into `sequencesRef` -- an *anchored* key, which
 * `isColumnUniversalId` does not recognize even though the SDK types it
 * `SUniversalPColumnId`. A kind that refused it would refuse the ids the block
 * itself writes, so applying a template exported from this block would fail.
 */
const ANCHORED_ID =
  '{"axes":[{"anchor":"main","idx":1}],"domain":{"pl7.app/alphabet":"aminoacid","pl7.app/vdj/feature":"CDR3"},"name":"pl7.app/vdj/sequence"}';

/** The other four serialized key forms `isColumnUniversalId` recognizes. */
const GLOBAL_ID = '{"__isRef":true,"blockId":"b1","name":"pl7.app/vdj/sequence"}';
const LOCAL_ID = '{"name":"pl7.app/vdj/sequence","resolvePath":["a","b"]}';
const FILTERED_ID = `{"__isFiltered":true,"axisFilters":[[0,"IGH"]],"source":${JSON.stringify(GLOBAL_ID)}}`;
const OVERRIDDEN_ID = `{"__isOverridden":true,"source":${JSON.stringify(GLOBAL_ID)},"specOverrides":{"annotations":{"pl7.app/label":"x"}}}`;

describe.each(["datasetRef", "embeddingRef"] as const)("%s", (field) => {
  it("accepts a PlRef", () => {
    expect(parse({ [field]: REF })).toEqual({ [field]: REF });
  });

  it.each([
    ["a column id", ANCHORED_ID],
    ["an object missing the marker", { blockId: "b1", name: "pf/dataset" }],
    ["a number", 42],
  ])("rejects %s", (_label, bad) => {
    expect(() => parse({ [field]: bad })).toThrow(`'${field}' must be a reference`);
  });
});

describe("sequencesRef", () => {
  it.each([
    ["an anchored id, as sequenceOptions mints it", ANCHORED_ID],
    ["a global key id", GLOBAL_ID],
    ["a local key id", LOCAL_ID],
    ["a filtered key id", FILTERED_ID],
    ["an overridden key id", OVERRIDDEN_ID],
  ])("accepts %s", (_label, id) => {
    expect(parse({ sequencesRef: [id] })).toEqual({ sequencesRef: [id] });
  });

  it("accepts an empty array -- the derivation legitimately yields none", () => {
    expect(parse({ sequencesRef: [] })).toEqual({ sequencesRef: [] });
  });

  it("accepts several ids, as a paired-chain embedding produces", () => {
    const sequencesRef = [ANCHORED_ID, GLOBAL_ID];
    expect(parse({ sequencesRef })).toEqual({ sequencesRef });
  });

  it.each([
    ["a bare id rather than an array", ANCHORED_ID],
    ["a string that is not JSON", ["pl7.app/vdj/sequence"]],
    ["malformed JSON", ['{"name":"pl7.app/vdj/sequence"']],
    ["JSON that is not a column key", ['{"foo":1}']],
    ["JSON that is not an object", ['"pl7.app/vdj/sequence"']],
    ["a number in the array", [42]],
    ["the key form rather than its serialization", [{ name: "x", resolvePath: [] }]],
  ])("rejects %s", (_label, sequencesRef) => {
    expect(() => parse({ sequencesRef })).toThrow("'sequencesRef' must be an array");
  });
});

describe("the HDBSCAN knobs", () => {
  it.each([2, 3, 50])("accepts minClusterSize %s", (minClusterSize) => {
    expect(parse({ minClusterSize })).toEqual({ minClusterSize });
  });

  it.each([1, 0, -2, 2.5, Number.NaN, "2"])(
    "rejects minClusterSize %s -- two points are the fewest that can form a group",
    (minClusterSize) => {
      expect(() => parse({ minClusterSize })).toThrow("'minClusterSize' must be an integer");
    },
  );

  it.each([true, false])("accepts rescueNoise %s", (rescueNoise) => {
    expect(parse({ rescueNoise })).toEqual({ rescueNoise });
  });

  it.each(["true", 1, null])("rejects rescueNoise %s", (rescueNoise) => {
    expect(() => parse({ rescueNoise })).toThrow("'rescueNoise' must be a boolean.");
  });
});

describe("the resource overrides", () => {
  it.each([1, 64, 1012])("accepts mem %s", (mem) => {
    expect(parse({ mem })).toEqual({ mem });
  });

  it.each([0, 1013, 1.5, "64"])("rejects mem %s", (mem) => {
    expect(() => parse({ mem })).toThrow("'mem' must be an integer between 1 and 1012");
  });

  it.each([1, 8, 128])("accepts cpu %s", (cpu) => {
    expect(parse({ cpu })).toEqual({ cpu });
  });

  it.each([0, 129, 2.5, "8"])("rejects cpu %s", (cpu) => {
    expect(() => parse({ cpu })).toThrow("'cpu' must be an integer between 1 and 128");
  });
});

describe("the params envelope", () => {
  it("accepts an empty object -- every field is optional", () => {
    expect(parse({})).toEqual({});
  });

  it("accepts a dataset picked with no embedding chosen yet", () => {
    expect(parse({ datasetRef: REF })).toEqual({ datasetRef: REF });
  });

  it("accepts a fully configured block", () => {
    const params = {
      datasetRef: REF,
      embeddingRef: { __isRef: true as const, blockId: "b2", name: "pf/embedding" },
      sequencesRef: [ANCHORED_ID],
      minClusterSize: 5,
      rescueNoise: false,
      mem: 128,
      cpu: 16,
      customBlockLabel: "ESM2, mcs:5",
    };
    expect(parse(params)).toEqual(params);
  });

  it("drops keys the contract does not name", () => {
    expect(parse({ minClusterSize: 2, notAParam: "x" })).toEqual({ minClusterSize: 2 });
  });

  it("rejects params that are not an object", () => {
    expect(() => parse(null)).toThrow();
    expect(() => parse([REF])).toThrow();
    expect(() => parse(5)).toThrow();
  });

  it("rejects a customBlockLabel that is not a string", () => {
    expect(() => parse({ customBlockLabel: 42 })).toThrow("'customBlockLabel' must be a string.");
  });
});
