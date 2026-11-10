// Entry point the host calls after loading this assembly: the op table.
using System.Collections.Generic;

namespace FmAssistant;

internal static class OpsEntry
{
    /// Raw property reads can reach values the manager cannot see (hidden attributes): discovery only, while
    /// ~/.fm-assistant/dev-nav exists.
    private static OpHandler DevOnly(OpHandler h) => (a, ct) => Nav.DevGuids ? h(a, ct)
        : throw new OpException("bad-request", "discovery op: dev mode only (~/.fm-assistant/dev-nav)");

    /// UI-driving ops run one at a time (Nav.UiLock).
    private static OpHandler Exclusive(OpHandler h) => async (a, ct) =>
    {
        await Nav.UiLock.WaitAsync(ct);
        try { return await h(a, ct); }
        finally { Nav.UiLock.Release(); }
    };

    internal static Dictionary<string, (OpHandler Handler, int TimeoutSeconds)> Ops() => new()
    {
        ["hello"] = (Meta.Hello, 10),
        ["panels"] = (Meta.Panels, 10),   // reload smoke: comment only
        ["ui_dump"] = (Meta.UiDump, 10),
        ["prop_check"] = (DevOnly(Meta.PropCheck), 10),
        ["tree"] = (DevOnly(Meta.Tree), 10),
        ["read"] = (DevOnly(Meta.Read), 60),
        ["list_rows"] = (Meta.ListRows, 15),
        ["load_recent_save"] = (GameOps.LoadRecentSave, 10),
        ["nav_open"] = (Exclusive(Nav.Open), 30),
        ["club"] = (Club.Read, 30),
        ["squad"] = (Squad.Read, 90),
        ["staff_search"] = (Exclusive(Staff.Search), 90),
        ["player_search"] = (Exclusive(Players.Search), 90),
        ["training"] = (Exclusive(Training.Read), 60),
        ["form"] = (Form.Read, 90),
        ["fixtures"] = (Fixtures.Read, 60),
        ["loans"] = (Loans.Read, 60),
        ["ctx_check"] = (Contexts.Check, 30),
        ["inbox"] = (Inbox.Read, 30),
        ["tactic"] = (Tactic.Read, 30),
        ["ctx_probe"] = (DevOnly(Spike.CtxProbe), 10),
        ["ctx_names"] = (DevOnly(Spike.CtxNames), 10),
        ["stars_dump"] = (DevOnly(Spike.StarsDump), 10),
        ["stars_settings"] = (DevOnly(Spike.StarsSettings), 10),
        ["ui_texts"] = (DevOnly(Spike.UiTexts), 10),
        ["profile_info"] = (DevOnly(Spike.ProfileInfo), 10),
        ["tree_probe"] = (DevOnly(Spike.TreeProbe), 10),
        ["profile_open"] = (DevOnly(Exclusive(Spike.ProfileOpen)), 20),
        ["team_panel_open"] = (DevOnly(Exclusive(Spike.TeamPanelOpen)), 20),
        ["negotiation"] = (Act.Negotiation, 15),
        ["act_shortlist_add"] = (Exclusive(Act.Gated("act_shortlist_add", Act.ShortlistAddOp)), 60),
        ["act_shortlist_remove"] = (Exclusive(Act.Gated("act_shortlist_remove", Act.ShortlistRemoveOp)), 60),
        ["act_staff_approach"] = (Exclusive(Act.Gated("act_staff_approach", Act.StaffApproachOp)), 60),
        ["act_staff_offer"] = (Exclusive(Act.Gated("act_staff_offer", Act.StaffOfferOp)), 60),
        ["act_scout_request"] = (Exclusive(Act.Gated("act_scout_request", Act.ScoutRequestOp)), 60),
        ["act_contract_open"] = (Exclusive(Act.Gated("act_contract_open", Act.ContractOpenOp)), 60),
        ["act_contract_offer"] = (Exclusive(Act.Gated("act_contract_offer", Act.ContractOfferOp)), 60),
        ["act_training_focus"] = (Exclusive(Act.Gated("act_training_focus", Act.TrainingFocusOp)), 60),
        ["act_training_sessions"] = (Exclusive(Act.Gated("act_training_sessions", Act.TrainingSessionsOp)), 120),
    };
}
