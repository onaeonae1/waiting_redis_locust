import random
import string
import logging
from locust import HttpUser, TaskSet, task, between


# Helper Functions
def generate_device_id() -> str:
    """랜덤한 device_id 생성"""
    return "".join(random.choices(string.ascii_letters + string.digits, k=10))


def generate_phone_number() -> str:
    """랜덤한 전화번호 생성"""
    return "".join(random.choices(string.digits, k=10))


def select_booth_and_pin():
    """랜덤한 booth_id 와 pinNumber 선택"""
    booth_and_pin = {
        1: "1111",
        2: "2222",
    }
    booth_id = random.choice(list(booth_and_pin.keys()))
    return booth_id, booth_and_pin[booth_id]


class FestivalTasks(TaskSet):
    client: HttpUser
    waiting_id: int = None
    check_count: int = 0
    max_checks: int = 10
    cancel_check_range: int = random.randint(5, 7)

    def on_start(self):
        """사용자 시작 시 초기화"""
        self.device_id = generate_device_id()
        self.booth_id, self.pin_number = select_booth_and_pin()

        self.waiting_data = {
            "boothId": self.booth_id,
            "tel": generate_phone_number(),
            "deviceId": self.device_id,
            "partySize": random.randint(1, 5),
            "pinNumber": self.pin_number,
        }

        # 웨이팅 생성
        self.create_waiting()

    @task(5)
    def get_booth_waiting_list(self):
        """특정 부스의 예약된 웨이팅 목록 조회"""
        res = self.client.get(f"/waiting/{self.booth_id}/reserved")
        if res.status_code != 200:
            logging.error(f"부스 웨이팅 조회 실패: {res.text}")

    @task(10)
    def check_my_waiting_status(self):
        """내 웨이팅 상태 조회 및 취소 처리"""
        if self.waiting_id and self.check_count < self.max_checks:
            res = self.client.get(
                f"/waiting/me/{self.device_id}", name="my waiting(REDIS)"
            )
            self.check_count += 1

            waiting_list = res.json().get("data", [])
            if waiting_list:
                waiting_num = waiting_list[0].get("waitingOrder", 999)
                logging.info(
                    f"[REDIS 기반 조회 {self.waiting_id}] 횟수: {self.check_count} | 순번: {waiting_num}"
                )

            if self.check_count == self.cancel_check_range:
                self.cancel_waiting()
        else:
            self.interrupt()

    @task(10)
    def check_my_waiting_status_rdb(self):
        if self.waiting_id and self.check_count < self.max_checks:
            res = self.client.get(
                f"/waiting/db/{self.device_id}", name="my waiting(RDB)"
            )
            self.check_count += 1
            waiting_list = res.json().get("data", [])
            if waiting_list:
                waiting_num = waiting_list[0].get("waitingOrder", 999)
                logging.info(
                    f"[RDB 기반 조회 {self.waiting_id}] 횟수: {self.check_count} | 순번: {waiting_num}"
                )

            if self.check_count == self.cancel_check_range:
                self.cancel_waiting()

        else:
            self.interrupt()

    def create_waiting(self):
        """웨이팅 생성"""
        res = self.client.post("/waiting", json=self.waiting_data)
        if res.status_code == 200:
            data = res.json().get("data", {})
            self.waiting_id = data.get("waitingId")
            if self.waiting_id:
                logging.info(f"웨이팅 생성 성공: ID {self.waiting_id}")
            else:
                logging.error(f"웨이팅 생성 실패: ID 획득 불가")
                self.interrupt()
        else:
            logging.error(f"웨이팅 생성 실패: {res.text}")
            self.interrupt()

    def cancel_waiting(self):
        """웨이팅 취소 요청"""
        if self.waiting_id:
            cancel_data = {"waitingId": self.waiting_id, "deviceId": self.device_id}
            res = self.client.put("/waiting", json=cancel_data)
            if res.status_code == 200:
                logging.info(f"웨이팅 취소 성공: {self.waiting_id}")
            else:
                logging.error(f"웨이팅 취소 실패: {res.text}")

            self.check_count = self.max_checks
        logging.info(f"User with {self.waiting_id} EXIT!! ")
        self.user.stop(True)


class FestivalUser(HttpUser):
    tasks = [FestivalTasks]
    host = ""  # 테스트 서버
    wait_time = between(1, 3)  # 요청 간 대기 시간 설정
