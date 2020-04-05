#!/usr/bin/env python
# -*- coding: utf-8 -*-

import binascii
import csv
import datetime
import os
import struct
import sys

import nfc

sys.path.append(os.path.dirname(os.path.abspath(__file__)) + '/nfcpy')

num_blocks = 20
service_code = 0x090f


class StationRecord(object):
    db = None

    def __init__(self, row):
        self.area_key = int(row[0], 10)
        self.line_key = int(row[1], 10)
        self.station_key = int(row[2], 10)
        self.company_value = row[3]
        self.line_value = row[4]
        self.station_value = row[5]

    @classmethod
    def get_none(cls):
        # 駅データが見つからないときに使う
        return cls(["0", "0", "0", "None", "None", "None"])

    @classmethod
    def get_db(cls, filename):
        # 駅データのcsvを読み込んでキャッシュする
        if cls.db == None:
            cls.db = []
            for row in csv.reader(open(filename, 'rU'),
                                  delimiter=',',
                                  dialect=csv.excel_tab):
                cls.db.append(cls(row))
        return cls.db

    @classmethod
    def get_station(cls, line_key, station_key):
        # 線区コードと駅コードに対応するStationRecordを検索する
        for station in cls.get_db("StationCode.csv"):
            if station.line_key == line_key and station.station_key == station_key:
                return station
        return cls.get_none()


class HistoryRecord(object):
    def __init__(self, data):
        # ビッグエンディアンでバイト列を解釈する
        row_be = struct.unpack('>2B2H4BH4B', data)
        # リトルエンディアンでバイト列を解釈する
        row_le = struct.unpack('<2B2H4BH4B', data)

        self.db = None
        self.console = self.get_console(row_be[0])
        self.process = self.get_process(row_be[1])
        self.year = self.get_year(row_be[3]) + 2000
        self.month = self.get_month(row_be[3])
        self.day = self.get_day(row_be[3])
        self.balance = row_le[8]

        self.in_station = StationRecord.get_station(row_be[4], row_be[5])
        self.out_station = StationRecord.get_station(row_be[6], row_be[7])

    @classmethod
    def get_console(cls, key):
        # よく使われそうなもののみ対応
        return {
            0x03: "精算機",
            0x04: "携帯型端末",
            0x05: "車載端末",
            0x12: "券売機",
            0x16: "改札機",
            0x1c: "乗継精算機",
            0xc8: "自販機",
        }.get(key)

    @classmethod
    def get_process(cls, key):
        # よく使われそうなもののみ対応
        return {
            0x01: "運賃支払",
            0x02: "チャージ",
            0x0f: "バス",
            0x46: "物販",
        }.get(key)

    @classmethod
    def get_year(cls, date):
        return (date >> 9) & 0x7f

    @classmethod
    def get_month(cls, date):
        return (date >> 5) & 0x0f

    @classmethod
    def get_day(cls, date):
        return (date >> 0) & 0x1f


class Station():
    def __init__(self, station, company, line):
        self.station = station
        self.company = company
        self.line = line


class SuicaRecord():
    def __init__(self, history):
        self.console = history.console
        self.process = history.process
        self.date = datetime.datetime(history.year, history.month, history.day)
        self.in_station = Station(history.in_station.station_value,
                                  history.in_station.company_value,
                                  history.in_station.line_value)
        self.out_station = Station(history.out_station.station_value,
                                   history.out_station.company_value,
                                   history.out_station.line_value)
        self.balance = history.balance
        self.payment = 0


class Suica():
    def __init__(self):
        clf = nfc.ContactlessFrontend('usb')
        self.data = []
        clf.connect(rdwr={'on-connect': self.__connected})
        self.__calculate_payment()
        self.data = self.data[1:]
        self.data = self.data[::-1]

    def __calculate_payment(self):
        for record_, record in zip(self.data[:-1], self.data[1:]):
            record.payment = record.balance - record_.balance

    def __connected(self, tag):

        if not isinstance(tag, nfc.tag.tt3.Type3Tag):
            print("error: tag isn't Type3Tag")
            return

        try:
            sc = nfc.tag.tt3.ServiceCode(service_code >> 6,
                                         service_code & 0x3f)
            for i in range(num_blocks):
                bc = nfc.tag.tt3.BlockCode(i, service=0)
                data = tag.read_without_encryption([sc], [bc])
                history = HistoryRecord(bytes(data))
                self.data.append(SuicaRecord(history))

        except Exception as e:
            print("error: %s" % e)


if __name__ == "__main__":
    suica = Suica()

    for d in suica.data:
        print()
        print("支払い: %s円" % d.payment)
        print("端末種: %s" % d.console)
        print("処理: %s" % d.process)
        print("日付: %02d-%02d-%02d" % (d.date.year, d.date.month, d.date.day))
        print("入線区: %s-%s" % (d.in_station.company, d.in_station.line))
        print("入駅順: %s" % d.in_station.station)
        print("出線区: %s-%s" % (d.out_station.company, d.out_station.line))
        print("出駅順: %s" % d.out_station.station)
        print("残高: %d" % d.balance)
