export type ToolDefinition = {
  id: string;
  translationKey: "pattern" | "stitch" | "future";
  analyticsEvent?: "portal_pattern_selected" | "portal_stitch_selected";
  href?: string;
  available: boolean;
  visible: boolean;
};

export function getToolDefinitions(
  patternUrl: string,
  stitchUrl: string,
  showFutureTools: boolean,
): ToolDefinition[] {
  return [
    {
      id: "pattern-translator",
      translationKey: "pattern",
      analyticsEvent: "portal_pattern_selected",
      href: patternUrl,
      available: true,
      visible: true,
    },
    {
      id: "stitch-translator",
      translationKey: "stitch",
      analyticsEvent: "portal_stitch_selected",
      href: stitchUrl,
      available: true,
      visible: true,
    },
    {
      id: "future-tool-one",
      translationKey: "future",
      available: false,
      visible: showFutureTools,
    },
    {
      id: "future-tool-two",
      translationKey: "future",
      available: false,
      visible: showFutureTools,
    },
  ];
}
