namespace PicoMultiModalCapture
{
    // 全局常量：关键点命名集中管理。
    // 命名与实际 SDK 枚举严格对应，避免导出数据的语义错位。
    public static class CaptureConst
    {
        // 手部 26 关键点：对应 Unity XR Hands 的 XRHandJointID 索引 0..25
        // （XRHandJointID.BeginMarker.ToIndex() == 0 起，至 EndMarker 前一个）
        public static readonly string[] HandJointNames = new string[]
        {
            "Wrist", "Palm",
            "ThumbMetacarpal", "ThumbProximal", "ThumbDistal", "ThumbTip",
            "IndexMetacarpal", "IndexProximal", "IndexIntermediate", "IndexDistal", "IndexTip",
            "MiddleMetacarpal", "MiddleProximal", "MiddleIntermediate", "MiddleDistal", "MiddleTip",
            "RingMetacarpal", "RingProximal", "RingIntermediate", "RingDistal", "RingTip",
            "LittleMetacarpal", "LittleProximal", "LittleIntermediate", "LittleDistal", "LittleTip"
        };

        // 全身 24 关键点：对应 PICO OpenXR SDK 的 BodyTrackerRole 枚举（索引 0..23）
        // 注意：0..15 为 leg tracking 模式即可返回，16..23 需 full body 模式。
        public static readonly string[] BodyJointNames = new string[]
        {
            "Pelvis", "LeftHip", "RightHip", "Spine1",
            "LeftKnee", "RightKnee", "Spine2", "LeftAnkle",
            "RightAnkle", "Spine3", "LeftFoot", "RightFoot",
            "Neck", "LeftCollar", "RightCollar", "Head",
            "LeftShoulder", "RightShoulder", "LeftElbow", "RightElbow",
            "LeftWrist", "RightWrist", "LeftHand", "RightHand"
        };

        public const int HandJointCount = 26;
        public const int BodyJointCount = 24;
    }
}
