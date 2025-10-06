import dlib
import numpy as np
import cv2
import os
import pandas as pd
import time
import logging
import sqlite3
import datetime
from xls_attendance.marking_attendance_in_xls import mark_attendance
from xls_attendance.voice_call_of_name import call_name

# Load models
detector = dlib.get_frontal_face_detector()
predictor = dlib.shape_predictor('data/data_dlib/shape_predictor_68_face_landmarks.dat')
face_reco_model = dlib.face_recognition_model_v1("data/data_dlib/dlib_face_recognition_resnet_model_v1.dat")

# Initialize DB and attendance table
conn = sqlite3.connect("attendance.db")
cursor = conn.cursor()
cursor.execute("CREATE TABLE IF NOT EXISTS attendance (name TEXT, UNIQUE(name))")
conn.commit()
conn.close()


class Face_Recognizer:
    def __init__(self):
        self.font = cv2.FONT_HERSHEY_SIMPLEX
        self.frame_cnt = 0
        self.fps = 0
        self.fps_show = 0
        self.frame_start_time = time.time()
        self.start_time = time.time()

        self.face_features_known_list = []
        self.face_name_known_list = []

        self.last_frame_face_centroid_list = []
        self.current_frame_face_centroid_list = []

        self.last_frame_face_name_list = []
        self.current_frame_face_name_list = []

        self.reclassify_interval_cnt = 0
        self.reclassify_interval = 10
        self.threshold = 0.5  # Tunable threshold for face recognition

    def get_face_database(self):
        if not os.path.exists("data/features_all.csv"):
            logging.error("features_all.csv not found in data/")
            return 0

        csv_rd = pd.read_csv("data/features_all.csv", header=None)
        for i in range(csv_rd.shape[0]):
            name = csv_rd.iloc[i][0]
            features = []
            for j in range(1, 129):
                val = csv_rd.iloc[i][j]
                features.append(float(val) if val != '' else 0.0)
            self.face_name_known_list.append(name)
            self.face_features_known_list.append(features)

        print(f"Loaded {len(self.face_name_known_list)} known faces.")
        return 1

    def update_fps(self):
        now = time.time()
        self.fps = 1.0 / (now - self.frame_start_time + 1e-5)
        self.frame_start_time = now

    def return_euclidean_distance(self, f1, f2):
        return np.linalg.norm(np.array(f1) - np.array(f2))

    def draw_note(self, img, faces_count):
        cv2.putText(img, "Face Recognizer", (50, 50), self.font, 1.2, (255, 255, 255), 2)
        cv2.putText(img, f"Frame: {self.frame_cnt}", (50, 100), self.font, 0.8, (0, 255, 0), 2)
        cv2.putText(img, f"FPS: {self.fps:.2f}", (50, 130), self.font, 0.8, (0, 255, 0), 2)
        cv2.putText(img, f"Faces: {faces_count}", (50, 160), self.font, 0.8, (0, 255, 0), 2)
        cv2.putText(img, "Press 'q' to Quit", (50, 190), self.font, 0.8, (0, 100, 255), 2)

    def attendance(self, name):
        conn = sqlite3.connect("attendance.db")
        cursor = conn.cursor()
        cursor.execute("INSERT OR IGNORE INTO attendance (name) VALUES (?)", (name,))
        conn.commit()
        conn.close()
        print(f"[Attendance] Marked: {name}")

    def extract_and_drop_table(self):
        conn = sqlite3.connect("attendance.db")
        cursor = conn.cursor()
        cursor.execute("SELECT name FROM attendance")
        rows = cursor.fetchall()
        cursor.execute("DROP TABLE IF EXISTS attendance")
        conn.commit()
        conn.close()
        return [row[0] for row in rows]

    def process(self, stream):
        if not self.get_face_database():
            return

        end_time = time.time() + 300
        while stream.isOpened() and time.time() < end_time:
            self.frame_cnt += 1
            ret, img = stream.read()
            if not ret:
                print("Failed to capture frame.")
                break

            key = cv2.waitKey(1)
            faces = detector(img, 0)
            self.last_frame_face_name_list = self.current_frame_face_name_list[:]
            self.last_frame_face_centroid_list = self.current_frame_face_centroid_list[:]
            self.current_frame_face_name_list = []
            self.current_frame_face_centroid_list = []

            for k, d in enumerate(faces):
                shape = predictor(img, d)
                face_descriptor = face_reco_model.compute_face_descriptor(img, shape)
                distances = [self.return_euclidean_distance(face_descriptor, known_face)
                             for known_face in self.face_features_known_list]

                if distances and min(distances) < self.threshold:
                    matched_idx = distances.index(min(distances))
                    name = self.face_name_known_list[matched_idx]
                    self.attendance(name)
                else:
                    name = "Unknown"

                self.current_frame_face_name_list.append(name)
                self.current_frame_face_centroid_list.append(
                    [(d.left() + d.right()) / 2, (d.top() + d.bottom()) / 2]
                )

                cv2.rectangle(img, (d.left(), d.top()), (d.right(), d.bottom()), (0, 255, 0), 2)
                cv2.putText(img, name, (d.left(), d.top() - 10), self.font, 0.8, (0, 255, 255), 2)

            self.update_fps()
            self.draw_note(img, len(faces))

            remaining = int(end_time - time.time())
            cv2.putText(img, f"Time Left: {remaining // 60}:{remaining % 60:02}", (50, 220), self.font, 0.8, (0, 255, 0), 2)

            if key == ord('q'):
                break

            cv2.imshow("camera", img)

    def run(self, courseId):
        cap = cv2.VideoCapture(0)
        self.process(cap)
        cap.release()
        cv2.destroyAllWindows()
        names = self.extract_and_drop_table()
        call_name(mark_attendance(courseId, names))


def attendance_taker(courseId):
    logging.basicConfig(level=logging.INFO)
    recognizer = Face_Recognizer()
    recognizer.run(courseId)


if __name__ == "__main__":
    attendance_taker("CSE101")
