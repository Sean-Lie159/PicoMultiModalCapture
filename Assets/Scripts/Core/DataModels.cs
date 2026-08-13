using System.Collections.Generic;

namespace PicoMultiModalCapture
{
    // 单帧内一个关节的采样（位置+四元数+半径/置信度，按模态选用）
    public struct JointSample
    {
        public int id;
        public float px, py, pz;
        public float qx, qy, qz, qw;
        public float radius;     // 手部关节半径（米）
        public float confidence; // 身体关节置信度
    }

    public struct HeadSample
    {
        public float px, py, pz;
        public float qx, qy, qz, qw;
        public float confidence;
    }

    public struct HandSample
    {
        public bool tracked;
        public float scale;
        public List<JointSample> joints;
    }

    public struct FrameSample
    {
        public double t;             // 相对录制起点的时间（秒，高精度）
        public string wallClock;     // UTC ISO8601 时间戳（便于跨设备对齐）
        public HeadSample head;
        public bool hasBody;
        public float bodyConfidence;
        public List<JointSample> bodyJoints;
        public HandSample leftHand;
        public HandSample rightHand;
    }
}
