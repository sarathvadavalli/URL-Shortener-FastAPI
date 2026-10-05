import time
import threading

class IDGenerator:
    def __init__(self):
        self.sequence = 0
        self.last_timestamp = -1
        self.lock = threading.Lock()

    def wait_next_millisecond(self, last_timestamp):
        timestamp = int(time.time() * 1000)

        while timestamp <= last_timestamp:
            timestamp = int(time.time() * 1000)

        return timestamp

    def next_id(self) -> int:
        # Lock used to ensure only 1 request enters the critical section at a time
        with self.lock:
            # Generating UNIX-based timestamp
            timestamp = int(time.time() * 1000)

            if timestamp == self.last_timestamp: # Handling requests arriving at same millisecond
                self.sequence += 1

                if self.sequence >= 1024:
                    # If no. of requests exceed 1024 per ms, it waits for the next ms
                    timestamp = self.wait_next_millisecond(self.last_timestamp)
                    self.sequence = 0
            else:
                self.sequence = 0

            # Tracking the timestamp of last request which is processed
            self.last_timestamp = timestamp

            # Reserving 10 bits for sequence number
            # Assuming 2^10 = 1024 unique ids can be generated within a millisecond
            return (timestamp << 10) | self.sequence