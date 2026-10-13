// SPDX-License-Identifier: MIT
// Copyright 2026 Lyle Mills
#ifndef EURORACK_PATTERNS_PRESENCE_H_
#define EURORACK_PATTERNS_PRESENCE_H_

#include <cstdint>
#include <limits>

namespace eurorack_patterns {

// One observation of the current probe bit and the corresponding fresh input.
// The caller owns probe generation, conversion, and sequence checking.
enum class PresenceEvidence { kMatch, kMismatch, kInvalid };

enum class PresenceStartupPolicy {
  // The first complete valid window publishes either state. Subsequent bad
  // windows require bad_windows_required consecutive windows.
  kFirstWindowDecides,
  // Even at startup, patched needs bad_windows_required bad windows.
  // One good window still publishes unpatched.
  kRequireStreak
};

struct PresenceConfig {
  uint16_t window_size;
  uint16_t mismatch_threshold;  // A window is bad at >= this many mismatches.
  uint16_t bad_windows_required;
  PresenceStartupPolicy startup_policy;
};

struct PresenceStartup {
  bool known;
  bool patched;  // Used only when known is true.
};

// One instance per channel. All methods must be called by one owner, or under
// caller-provided synchronization. No allocation or exceptions.
class PresenceDetector {
 public:
  PresenceDetector()
      : config_{0, 0, 0, PresenceStartupPolicy::kRequireStreak},
        configured_(false), ready_(false), patched_(false),
        first_window_pending_(true), observations_(0), mismatches_(0),
        bad_windows_(0), windows_(0), last_mismatches_(0) {}

  // Invalid configuration returns false and leaves this instance unchanged.
  // Configure resets all accumulated evidence and published state.
  bool Configure(const PresenceConfig& config, const PresenceStartup& startup) {
    if (config.window_size == 0 || config.mismatch_threshold == 0 ||
        config.mismatch_threshold > config.window_size ||
        config.bad_windows_required == 0 ||
        (config.startup_policy != PresenceStartupPolicy::kFirstWindowDecides &&
         config.startup_policy != PresenceStartupPolicy::kRequireStreak)) {
      return false;
    }
    config_ = config;
    configured_ = true;
    ready_ = startup.known;
    patched_ = startup.known && startup.patched;
    first_window_pending_ = true;
    observations_ = 0;
    mismatches_ = 0;
    bad_windows_ = 0;
    windows_ = 0;
    last_mismatches_ = 0;
    return true;
  }

  // Invalid evidence (including a missing/duplicate frame) discards a partial
  // window and the bad-window streak. It never changes the published state.
  // Returns true only when a complete valid window has been evaluated.
  bool Observe(PresenceEvidence evidence) {
    if (!configured_) return false;
    if (evidence == PresenceEvidence::kInvalid) {
      observations_ = 0;
      mismatches_ = 0;
      bad_windows_ = 0;
      return false;
    }
    if (evidence != PresenceEvidence::kMatch &&
        evidence != PresenceEvidence::kMismatch) {
      // Fail closed for an unrecognized enum value as well.
      observations_ = 0;
      mismatches_ = 0;
      bad_windows_ = 0;
      return false;
    }
    if (evidence == PresenceEvidence::kMismatch) ++mismatches_;
    if (++observations_ < config_.window_size) return false;

    last_mismatches_ = mismatches_;
    observations_ = 0;
    mismatches_ = 0;
    if (windows_ < std::numeric_limits<uint32_t>::max()) ++windows_;

    const bool bad = last_mismatches_ >= config_.mismatch_threshold;
    if (!bad) {
      bad_windows_ = 0;
      patched_ = false;
      ready_ = true;
    } else {
      if (bad_windows_ < config_.bad_windows_required) ++bad_windows_;
      if ((first_window_pending_ &&
           config_.startup_policy == PresenceStartupPolicy::kFirstWindowDecides) ||
          bad_windows_ >= config_.bad_windows_required) {
        patched_ = true;
        ready_ = true;
      }
    }
    first_window_pending_ = false;
    return true;
  }

  bool configured() const { return configured_; }
  bool ready() const { return ready_; }
  bool patched() const { return patched_; }
  uint16_t observations() const { return observations_; }
  uint16_t mismatches() const { return mismatches_; }
  uint16_t bad_windows() const { return bad_windows_; }
  uint32_t windows() const { return windows_; }
  uint16_t last_mismatches() const { return last_mismatches_; }

 private:
  PresenceConfig config_;
  bool configured_;
  bool ready_;
  bool patched_;
  bool first_window_pending_;
  uint16_t observations_;
  uint16_t mismatches_;
  uint16_t bad_windows_;
  uint32_t windows_;
  uint16_t last_mismatches_;
};

}  // namespace eurorack_patterns

#endif  // EURORACK_PATTERNS_PRESENCE_H_
