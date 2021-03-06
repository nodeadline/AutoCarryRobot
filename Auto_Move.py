from color_detector import ColorBounding
from Movement import Movement
import cv2
import time
import threading
from collections import deque
from face_detector import Face_detector
from face_recognize import Face_recognize
# from rectangle_judgement import ShapeAnalysis
from wzy_rectangle_detector import ShapeAnalysis
from WaveModule import Wave
import random

lock = threading.Lock()
# 640*480
MID_WIDTH = 320
MID_HEIGHT = 240
ALL_AREA = 640 * 480


class MonitorThread(threading.Thread):
    def __init__(self, input):
        super(MonitorThread).__init__()
        self._jobq = input
        # 创建一个窗口
        self.cap = cv2.VideoCapture(0)
        threading.Thread.__init__(self)

    def run(self):
        cv2.namedWindow('camera', flags=cv2.WINDOW_NORMAL | cv2.WINDOW_FREERATIO)
        while self.cap.isOpened():
            ret, frame = self.cap.read()
            # frame = cv2.flip(frame, -1, dst=None)  # 垂直镜像
            cv2.waitKey(5)
            lock.acquire()
            if len(self._jobq) == 10:
                self._jobq.popleft()
            else:
                self._jobq.append(frame)
            lock.release()
            cv2.imshow('camera', frame)
            if cv2.waitKey(1) == ord('q'):
                # 退出程序
                break
        print("实时读取线程退出！！！！")
        cv2.destroyWindow('camera')
        self._jobq.clear()  # 读取进程结束时清空队列
        self.cap.release()


class AutoMoveThread(threading.Thread):
    def __init__(self, input):
        super(AutoMoveThread).__init__()
        self._jobq = input
        self.cb = ColorBounding()
        self.mv = Movement()
        self.fa = Face_detector()
        self.sa = ShapeAnalysis()
        self.fad = Face_recognize()
        self.buffer = list()
        self.wave = Wave()
        threading.Thread.__init__(self)

        self.isFind = False  # 是否找到三个物体中有正确人脸的目标物体，在找到目标人脸后置为True
        self.isFinal = False  # 整体搬运流程结束，退出循环
        self.test_flag = 0

    def run(self):
        # 定义随机寻找顺序
        color = ['red', 'yellow', 'green']
        # random.shuffle(color)

        while not self.isFinal and color:
            color_now = color[0]
            color.pop(0)
            self.implement(color_now)

    def implement(self, color):
        flag = False
        circle_flag = False
        signal = False
        self.mv.take_action(1)
        time.sleep(5)
        print("Now color: ", color)
        while True:
            if len(self._jobq) != 0:
                lock.acquire()
                frame_new = self._jobq.pop()
                lock.release()
                flag = True

                """
                    找color物体
                """
                if not circle_flag:
                    if self.getColorObjectPosition(frame_new, color) == (-1, -1):
                        self.mv.turn_left(10, 200)
                        time.sleep(0.5)
                        """
                            通过小幅度左右移使机器人位于X轴正中 
                            X轴正中：280 - 360

                        """
                    x_now, y_now = self.getColorObjectPosition(frame_new, color)
                    if self.getColorObjectPosition(frame_new, color) != (-1, -1):
                        if x_now >= 360:
                            # 偏右往右
                            self.mv.turn_right(10, 50)
                            time.sleep(0.5)
                        elif x_now <= 280:
                            # 偏左往左
                            self.mv.turn_left(10, 50)
                            time.sleep(0.5)
                        else:
                            """
                                这一步之前是已经移正图像，然后向前走到一定的距离
                                round = 450mm
                            """
                            self.mv.move_forward(10, 500)
                            distance = self.wave.getWaveData()
                            print('distance: ', distance)

                            if distance < 450 or self.getColorArea() / ALL_AREA >= 0.22:
                                print("Come On!")
                                circle_flag = True

                else:
                    """
                        转圈 + 找人脸
                        没找到人脸： 转圈 不检测矩形
                        找到人脸但是不是矩形： 以较小的速度继续转圈 并且持续检测矩形
                        找到人脸：前进
                    """
                    if not signal:
                        x_fa, y_fa = self.fa.face_find(frame_new)
                        if self.fa.face_find(frame_new) == (-1, -1):
                            """
                                Face not found, turn around
                            """
                            self.mv.left_ward()
                            self.mv.left_ward()
                            time.sleep(0.5)
                        else:
                            """
                                Find face and turn left/right
                                320 * 240
                            """
                            print('face x: ', x_fa, 'face y:', y_fa)
                            if x_fa >= 210:
                                # 偏右往右
                                self.mv.move_right(5, 100)
                                time.sleep(1)
                            elif x_fa <= 110:
                                # 偏左往左
                                self.mv.move_left(5, 100)
                                time.sleep(1)
                            else:
                                signal = True

                    else:
                        """
                            此处人脸已经对正，开始人脸识别
                            人脸识别正确：返回1, face_x, face_y, 执行物体搬运过程
                            人脸识别错误：返回0， -1， -1
                        """
                        print("开始人脸识别")
                        ret, posx, posy = self.fad.face_rec(frame_new)

                        if color == 'green':
                            ret = 1
                        else:
                            ret = 0

                        if ret:
                            self.moveObject()
                            self.isFind = True
                            print("搬运")
                        else:
                            # for test
                            self.leaveObject()
                            print("不搬运，撤退")
                        break

            elif flag and len(self._jobq) == 0:
                break

        if self.isFind:
            # 已经搬到想要的物体，执行搬到终点操作，同时isFinal置为True
            print("朝着终点搬运！")
            self.isFinal = True
            terminal_flag = False

            while True:
                if len(self._jobq) != 0:
                    lock.acquire()
                    frame = self._jobq.pop()
                    lock.release()
                    flag = True
                    x_now, y_now = self.getColorObjectPosition(frame, 'black')
                    if self.getColorObjectPosition(frame, 'black') == (-1, -1):
                        self.mv.turn_left(10, 200)
                        time.sleep(0.3)
                        """
                            通过小幅度左右移使机器人位于X轴正中 
                            X轴正中：280 - 360

                        """

                    if self.getColorObjectPosition(frame, 'black') != (-1, -1) and not terminal_flag:
                        if x_now >= 400:
                            # 偏右往右
                            self.mv.turn_right(10, 50)
                            time.sleep(0.5)
                        elif x_now <= 240:
                            # 偏左往左
                            self.mv.turn_left(10, 50)
                            time.sleep(0.5)
                        else:
                            terminal_flag = True
                    """
                        前进，抵达终点，放下物体
                    """
                    if terminal_flag:
                        self.mv.move_forward(15, 500)

                        if self.getColorArea() / ALL_AREA >= 0.05:
                            self.mv.move_forward(40, 2000)
                            time.sleep(10)
                            self.mv.move_forward(10, 1000)
                            time.sleep(10)
                            print("Terminal!")
                            self.mv.take_action(1)
                            time.sleep(10)
                            break

                elif flag and len(self._jobq) == 0:
                    break

    def getColorObjectPosition(self, frame, color):
        x, y = self.cb.bounding(frame, color)
        print("x:", x, "y:", y)
        return x, y

    def getColorArea(self):
        area = self.cb.red_area
        print('color_area ', area)
        return area

    def circleMove(self):
        self.mv.left_ward()

    def moveObject(self):
        self.mv.take_action(1)
        time.sleep(5)
        self.mv.move_forward(20, 2000)
        time.sleep(15)
        self.mv.take_action(0)
        time.sleep(10)

    def leaveObject(self):
        self.mv.move_backward(20, 2000)
        time.sleep(5)


if __name__ == "__main__":
    q = deque([], 10)
    th1 = MonitorThread(q)
    th2 = AutoMoveThread(q)
    th1.start()
    th2.start()  # 开启两个线程

    th1.join()
    th2.join()
