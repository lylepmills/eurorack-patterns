// SPDX-License-Identifier: MIT
// Copyright 2026 Lyle Mills
#include "../examples/daisy/diagnostics.h"
#include "../examples/daisy/load.h"
#include <cstdlib>
#include <cstring>
#include <type_traits>
static_assert(std::is_trivial<bench::TimingBucket>::value, "SDRAM must have no constructors");
static_assert(sizeof(bench::Record)*bench::kMaxRecords +
              (sizeof(bench::Bucket)+sizeof(bench::TimingBucket))*bench::kMaxBuckets <= 16*1024*1024,
              "Retained diagnostics must fit beside the original trace");
#define CHECK(x) do { if (!(x)) { std::fprintf(stderr,"FAIL line %d: %s\n",__LINE__,#x); std::exit(1); } } while (0)
static bench::Timing Sample(uint32_t seq, uint64_t ticks, uint32_t width = 9600) {
  // Nonzero origin and raw wrap. Fractional microseconds are retained in ticks.
  const uint32_t begin = uint32_t(ticks + 0xfffffff0ull);
  return {ticks, ticks+width, seq, uint32_t(ticks/240), uint32_t((ticks+width)/240-ticks/240),
          begin, begin+120, begin+160, begin+width, begin+width+120, begin+width+160};
}
int main(int argc, char** argv) {
  bench::Workload w; w.mode=2; w.duration=3600000; CHECK(w.Valid()); w.mode=3; CHECK(!w.Valid());
  bench::TimingBucket bucket; bucket.Reset();
  auto p = Sample(0,0); bucket.Add(p,p);
  auto t = Sample(1,240000); bucket.Add(p,t);
  CHECK(bucket.peak[bench::kIntervalUs].current.seq == 1);
  CHECK(bucket.peak[bench::kWorkUs].current.seq == 0); // tie keeps first
  p=t; t=Sample(2,480003,24000); bucket.Add(p,t);
  CHECK(bucket.peak[bench::kWorkUs].current.seq == 2);
  CHECK(bucket.peak[bench::kRiseIntervalTicks].current.seq == 2); // sub-us difference
  CHECK(bucket.peak[bench::kIntervalUs].current.seq == 1);
  p=t; t=Sample(3,720003); t.rise_after+=100; bucket.Add(p,t);
  CHECK(bucket.peak[bench::kRiseCallTicks].current.seq == 3);
  bucket.Bookkeeping(2,300); bucket.Bookkeeping(3,100);
  CHECK(bucket.max_bookkeeping_ticks==300 && bucket.bookkeeping_seq==2);
  bucket.Reset(); CHECK(!bucket.count);
  p=Sample(1799999,431999760000ull); t=Sample(1800000,432000000000ull);
  bucket.Add(p,t);
  CHECK(bucket.first.seq==1800000 && bucket.peak[bench::kIntervalUs].previous.seq==1799999);
  CHECK(bench::TimingMetric(bench::kIntervalUs,p,t)==1000);
  char line[512];
  CHECK(bench::FormatTiming(line,sizeof(line),1800,2,p,t)>0);
  CHECK(std::strstr(line,"431999760000") != nullptr); // no 32-bit truncation
  CHECK(bench::FormatTiming(line,10,1800,2,p,t)>=10); // caller detects truncation
  if (argc==2 && std::strcmp(argv[1],"--synthetic")==0) {
    p=Sample(0,0);
    for (unsigned second=0;second<2;++second) {
      bucket.Reset();
      for (unsigned i=0;i<1000;++i) {
        const uint32_t seq=second*1000+i;
        t=Sample(seq,uint64_t(seq)*240000); bucket.Add(p,t); p=t;
      }
      bucket.Bookkeeping(second*1000,100);
      std::printf("S,%u,1000,%u,%u,0,0,0,0,40,1000,1234,1235\n",second,second*1000000,second*1000000+999000);
      std::printf("T,%u,1000,100,%u\n",second,second*1000);
      for (unsigned k=0;k<bench::kTimingPeaks+2;++k) {
        const auto& a=k<2 ? (k ? bucket.last : bucket.first) : bucket.peak[k-2].previous;
        const auto& b=k<2 ? a : bucket.peak[k-2].current;
        const int n=bench::FormatTiming(line,sizeof(line),second,k,a,b);
        CHECK(n>0 && size_t(n)<sizeof(line)); std::fputs(line,stdout);
      }
    }
  } else std::puts("PASS: timing peak retention, predecessors, ties, wrap, long ticks and storage budget");
}
