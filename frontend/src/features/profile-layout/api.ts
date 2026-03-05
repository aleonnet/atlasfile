import {
  applyProjectLayout,
  fetchProfileHistory,
  fetchProjectProfile,
  planProjectLayout,
  updateProjectProfile,
  validateProjectProfile
} from "../../api";
import type { LayoutPlanResponse, ProfileHistoryEntry, ProjectProfileResponse, ProjectProfileV2 } from "./types";

export async function getProfile(projectRef: string): Promise<ProjectProfileResponse> {
  return fetchProjectProfile(projectRef);
}

export async function validateProfile(projectRef: string, profile: ProjectProfileV2): Promise<{ valid: boolean; profile: ProjectProfileV2 }> {
  return validateProjectProfile(projectRef, profile);
}

export async function saveProfile(projectRef: string, profile: ProjectProfileV2, ifMatchVersion: number): Promise<ProjectProfileResponse> {
  return updateProjectProfile(projectRef, profile, ifMatchVersion, "frontend:profile-workspace");
}

export async function getProfileHistory(projectRef: string): Promise<ProfileHistoryEntry[]> {
  const data = await fetchProfileHistory(projectRef);
  return data.entries ?? [];
}

export async function planLayout(
  projectRef: string,
  profile: ProjectProfileV2,
  options?: { strategy?: "rename_with_suffix" | "skip" | "overwrite"; cleanup_empty_dirs?: boolean }
): Promise<LayoutPlanResponse> {
  return planProjectLayout(projectRef, profile, options);
}

export async function applyLayout(
  projectRef: string,
  profile: ProjectProfileV2,
  planId: string,
  ifMatchVersion: number,
  options?: { strategy?: "rename_with_suffix" | "skip" | "overwrite"; cleanup_empty_dirs?: boolean }
) {
  return applyProjectLayout(projectRef, {
    profile,
    plan_id: planId,
    confirm: true,
    strategy: options?.strategy ?? "rename_with_suffix",
    cleanup_empty_dirs: options?.cleanup_empty_dirs ?? false,
    if_match_version: ifMatchVersion
  });
}

