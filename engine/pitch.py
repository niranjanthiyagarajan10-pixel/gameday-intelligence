"""Pitch geometry. Units are meters. Home attacks toward x = PITCH_LENGTH in the first half."""

PITCH_LENGTH = 105.0
PITCH_WIDTH = 68.0

GOAL_WIDTH = 7.32
GOAL_Y_LOW = (PITCH_WIDTH - GOAL_WIDTH) / 2
GOAL_Y_HIGH = (PITCH_WIDTH + GOAL_WIDTH) / 2

PENALTY_SPOT_DISTANCE = 11.0
BOX_DEPTH = 16.5
BOX_WIDTH = 40.32

# The ball can leave the field of play. Players in the simulation cannot.
BALL_MARGIN = 3.0

TRACKING_HZ = 5
