import { assertParamsObject, defineBlockKind } from "@platforma-sdk/block-kind";
import type { PlRef, SUniversalPColumnId } from "@platforma-sdk/model";
import {
  isAnchoredPColumnId,
  isColumnUniversalId,
  isPlRef,
  parseJsonSafely,
} from "@platforma-sdk/model";
import { name, version } from "../package.json" with { type: "json" };

/**
 * This block's init-params contract — everything a user sets by hand: the dataset,
 * the embedding column to cluster by, the HDBSCAN knobs, the resource overrides and
 * the subtitle they type.
 *
 * `sequencesRef` is here despite being derived rather than picked. The panel writes
 * it from the chosen embedding column, and the workflow reads it to decide whether
 * to emit centroid and alignment columns at all -- so a template that dropped it
 * would seed a block producing a different output shape than the one it was
 * exported from, until someone opened the settings panel and the derivation ran.
 *
 * `defaultBlockLabel` is absent: a `watchEffect` in `ui/src/app.ts` derives it from
 * the embedding column's option label, which only exists once the result pool has
 * resolved it.
 *
 * Every field is optional. A half-configured block is ordinary state the UI reaches
 * -- a dataset picked with no embedding chosen yet -- and the projection hands that
 * state back untouched, so a required field would break the export/apply round trip.
 */
export type BlockParams = {
  datasetRef?: PlRef;
  embeddingRef?: PlRef;
  sequencesRef?: SUniversalPColumnId[];
  minClusterSize?: number;
  rescueNoise?: boolean;
  mem?: number;
  cpu?: number;
  customBlockLabel?: string;
};

// Identity (`name`/`version`) comes from this package's own `package.json`, so
// the on-wire `{name}@{version}` reference can never drift from what npm
// publishes; the bundler inlines the JSON import.
export const kind = defineBlockKind<BlockParams>({
  name,
  version,
  parseInitializationParams,
});

// Internals

/** The same contract at runtime, for params arriving from a template file rather than typed code. */
function parseInitializationParams(value: unknown): BlockParams {
  assertParamsObject(value);

  const {
    datasetRef,
    embeddingRef,
    sequencesRef,
    minClusterSize,
    rescueNoise,
    mem,
    cpu,
    customBlockLabel,
  } = value;

  if (datasetRef !== undefined && !isPlRef(datasetRef)) {
    throw new Error(
      "'datasetRef' must be a reference to an upstream dataset, written as { block, name }.",
    );
  }
  // A PlRef rather than a column id, so the workflow can wire the producing block
  // in as an upstream.
  if (embeddingRef !== undefined && !isPlRef(embeddingRef)) {
    throw new Error("'embeddingRef' must be a reference to an embedding column.");
  }
  if (sequencesRef !== undefined) {
    if (!Array.isArray(sequencesRef) || !sequencesRef.every(isColumnId)) {
      throw new Error("'sequencesRef' must be an array of sequence column ids.");
    }
  }
  // HDBSCAN's minimum cluster size: two points are the fewest that can form a group.
  if (minClusterSize !== undefined && !isIntegerAtLeast(minClusterSize, 2)) {
    throw new Error("'minClusterSize' must be an integer greater than or equal to 2.");
  }
  if (rescueNoise !== undefined && typeof rescueNoise !== "boolean") {
    throw new Error("'rescueNoise' must be a boolean.");
  }
  // Memory 1-1012 GiB and CPU 1-128 cores in integer steps. The workflow forwards
  // both straight to resource scheduling, where a value outside them fails the run.
  if (mem !== undefined && !isIntegerInRange(mem, 1, 1012)) {
    throw new Error("'mem' must be an integer between 1 and 1012 (GiB).");
  }
  if (cpu !== undefined && !isIntegerInRange(cpu, 1, 128)) {
    throw new Error("'cpu' must be an integer between 1 and 128 (cores).");
  }
  if (customBlockLabel !== undefined && typeof customBlockLabel !== "string") {
    throw new Error("'customBlockLabel' must be a string.");
  }

  return {
    datasetRef,
    embeddingRef,
    sequencesRef: sequencesRef as SUniversalPColumnId[] | undefined,
    minClusterSize,
    rescueNoise,
    mem,
    cpu,
    customBlockLabel,
  };
}

/**
 * A column identifier as this block stores it: a canonically serialized JSON key.
 * `isColumnUniversalId` covers the key forms the SDK's id encoding uses, but the ids
 * here come from the `sequenceOptions` output, which mints *anchored* keys -- a shape
 * none of those recognizes even though the SDK types it `SUniversalPColumnId`. Both
 * forms are accepted, or the kind would refuse the ids the block itself writes into a
 * template.
 */
function isColumnId(value: unknown): value is SUniversalPColumnId {
  if (typeof value !== "string") return false;
  return isColumnUniversalId(value) || isAnchoredPColumnId(parseJsonSafely(value));
}

function isIntegerAtLeast(value: unknown, min: number): value is number {
  return typeof value === "number" && Number.isInteger(value) && value >= min;
}

function isIntegerInRange(value: unknown, min: number, max: number): value is number {
  return isIntegerAtLeast(value, min) && (value as number) <= max;
}
