import matplotlib.pyplot as plt

# حمّل البيانات من ملف
times = []
levels = []

with open("signal.csv") as f:
    for line in f:
        t, l = line.strip().split(",")
        times.append(int(t))
        levels.append(int(l))

# حوّلها إلى شكل موجي
signal = []
time_axis = []
current_time = 0

for i in range(len(times)):
    duration = times[i]
    level = levels[i]
    signal.extend([level] * duration)
    time_axis.extend([current_time + j for j in range(duration)])
    current_time += duration

plt.plot(time_axis, signal)
plt.title("RF Signal")
plt.xlabel("Time (μs)")
plt.ylabel("Level")
plt.grid(True)
plt.show()
