#!/usr/bin/python

from datetime import datetime

import chess
import chess.pgn
import chess.svg

import git

import numpy as np

from keras.layers import Input, Dense, Flatten, BatchNormalization, Dropout, Lambda, merge, Merge, Embedding
from keras.models import Model, Sequential
from keras.callbacks import TensorBoard, ModelCheckpoint
import keras.backend as K

class ChessNet:

    def __init__(self):
        self.pieces = [None] + [chess.Piece(piece_type, color)
                                for color in [True, False]
                                for piece_type in [chess.PAWN, chess.KNIGHT, chess.BISHOP, chess.ROOK, chess.QUEEN, chess.KING]]
        self.piece_dict = {piece: idx for idx, piece in enumerate(self.pieces)}

        self.board_score = self.initialize_model()

    def board_to_tensor(self, board):
        board_tensor = np.array([self.piece_dict[board.piece_at(square)] for square in chess.SQUARES], dtype='uint8')
        extra_state_tensor = np.array([
            board.turn,
            board.has_kingside_castling_rights(True), board.has_queenside_castling_rights(True),
            board.has_kingside_castling_rights(False), board.has_queenside_castling_rights(False)
        ], dtype='uint8')
        return board_tensor, extra_state_tensor

    def process_game(self, game):
        b = chess.Board()
        board_tensors = []
        extra_tensors = []
        targets = []

        def _add(move, target):
            b.push(move)
            bt, et = self.board_to_tensor(b)
            board_tensors.append(bt)
            extra_tensors.append(et)
            targets.append(target)
            b.pop()

        for selected_move in game.main_line():
            # Get a random legal move that was not selected
            legal_moves = np.array(list(b.legal_moves))
            np.random.shuffle(legal_moves)
            for legal_move in legal_moves:
                if legal_move != selected_move:
                    _add(legal_move, 0)
                    _add(selected_move, 1)
                    break
            b.push(selected_move)
        return np.array(board_tensors), np.array(extra_tensors), np.array(targets)

    def initialize_model(self):
        n = 1024

        # uint8 is ok for <= 256 classes, otherwise use int32
        #board_score.add(Input(shape=input_shape, dtype='uint8'))

        # Without the output_shape, Keras tries to infer it using calling the function
        # on an float32 input, which results in error in TensorFlow:
        #
        #   TypeError: DataType float32 for attr 'TI' not in list of allowed values: uint8, int32, int64

        board_one_hot = Sequential()
        nb_classes = len(self.pieces)
        input_shape = (64, )
        output_shape = (64, nb_classes)
        board_one_hot.add(Lambda(K.one_hot,
                                 arguments={'nb_classes': nb_classes},
                                 input_shape=input_shape, input_dtype='uint8',
                                 output_shape=output_shape))
        board_one_hot.add(Flatten())
        board_one_hot.add(BatchNormalization())

        extra = Sequential()
        extra.add(BatchNormalization(input_shape=(5, )))
#        extra.add(Dense(32, input_shape=(5, )))

        board_score = Sequential()
        merged_layer = Merge([board_one_hot, extra], mode='concat')
        board_score.add(merged_layer)

        board_score.add(Dense(n, activation='relu'))
        board_score.add(Dense(n, activation='relu'))
        board_score.add(Dense(n, activation='relu'))
        board_score.add(BatchNormalization())
        board_score.add(Dropout(0.2))

        board_score.add(Dense(n, activation='relu'))
        board_score.add(Dense(n, activation='relu'))
        board_score.add(Dense(n, activation='relu'))
        board_score.add(BatchNormalization())
        board_score.add(Dropout(0.2))

        board_score.add(Dense(n, activation='relu'))
        board_score.add(Dense(n, activation='relu'))
        board_score.add(Dense(n, activation='relu'))
        board_score.add(BatchNormalization())
        board_score.add(Dropout(0.2))

        board_score.add(Dense(n, activation='relu'))
        board_score.add(Dense(n, activation='relu'))
        board_score.add(Dense(n, activation='relu'))
        board_score.add(BatchNormalization())
        board_score.add(Dropout(0.2))

        board_score.add(Dense(n, activation='relu'))
        board_score.add(Dense(n, activation='relu'))
        board_score.add(Dense(n, activation='relu'))
        board_score.add(BatchNormalization())
        board_score.add(Dropout(0.2))

        board_score.add(Dense(1, activation='sigmoid'))

        board_score.compile(loss='binary_crossentropy', optimizer='adam', metrics=['accuracy'])

        print board_score.summary()

        return board_score

    def train_on_games(self, pgn, n_games):

        train_file = "train.npz"
        try:
            loaded = np.load(train_file)
            board_tensors = loaded['board_tensors']
            extra_tensors = loaded['extra_tensors']
            target_tensors = loaded['target_tensors']
            print "Loaded from {}".format(train_file)
        except IOError:
            pgn.seek(0)
            game_data = []
            for i in range(n_games):
                game = chess.pgn.read_game(pgn)
                game_data.append(self.process_game(game))
                if i % 100 == 0:
                    print "Loading game {}/{}".format(i, n_games)

            board_tensors = np.concatenate([gd[0] for gd in game_data])
            extra_tensors = np.concatenate([gd[1] for gd in game_data])
            target_tensors = np.concatenate([gd[2] for gd in game_data])

            n_samples = len(board_tensors)
            permutation = np.random.permutation(n_samples)
            board_tensors = board_tensors[permutation]
            extra_tensors = extra_tensors[permutation]
            target_tensors = target_tensors[permutation]

            np.savez_compressed(train_file, board_tensors=board_tensors,
                                extra_tensors=extra_tensors,
                                target_tensors=target_tensors)

        repo = git.Repo(".")
        savedir = 'logs/' + str(datetime.now()) + " " + repo.git.describe("--always", "--dirty", "--long")
        tbcb = TensorBoard(log_dir=savedir, histogram_freq=0, write_graph=True, write_images=False)
        mccb = ModelCheckpoint(savedir+'/model.{epoch:04d}-{val_loss:.2f}.hdf5', monitor='val_loss', save_best_only=True)
        cb = [tbcb, mccb]

        self.board_score.fit([board_tensors, extra_tensors], target_tensors, nb_epoch=1000, callbacks=cb,
                             batch_size=4096*2, validation_split=0.1)


def main():
    pgn = open("gorgobase.pgn")
    net = ChessNet()
    net.train_on_games(pgn, 50000)

    # games = 0
    # for offset, headers in chess.pgn.scan_headers(pgn):
    #     games += 1
    #     if games % 10000 == 0:
    #         print games
    # print games


if __name__ == '__main__':
    main()
