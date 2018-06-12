#!/usr/bin/env python
# encoding: utf-8


import sys
import time
import os
import numpy as np
import tensorflow as tf
from PrepareData import batch_index, load_w2v, load_data_for_Emotion_CNN
from Evalue import Emotion_eval
from Evalue import calibrated_label_ranking

FLAGS = tf.app.flags.FLAGS
tf.app.flags.DEFINE_integer('batch_size', 200, 'number of example per batch')
tf.app.flags.DEFINE_float('learning_rate', 0.005, 'learning rate')
tf.app.flags.DEFINE_float('keep_prob', 1.0, 'word embedding training dropout keep prob')
tf.app.flags.DEFINE_float('l2_reg', 0.0001, 'l2 regularization')

tf.app.flags.DEFINE_integer('display_step', 1, 'number of test display step')
tf.app.flags.DEFINE_integer('training_iter', 40, 'number of train iter')
tf.app.flags.DEFINE_integer('embedding_dim', 100, 'dimension of word embedding')
tf.app.flags.DEFINE_integer('n_class', 8, 'number of distinct class')
tf.app.flags.DEFINE_integer('max_doc_len', 90, 'max number of tokens per sentence')

tf.app.flags.DEFINE_string('train_file_path', 'renCECps_multi_class.txt', 'training file')
tf.app.flags.DEFINE_string('embedding_file_path', 'zh_embedding_100.txt', 'embedding file')
tf.app.flags.DEFINE_string('test_index', 1, 'test_index')
tf.app.flags.DEFINE_string('embedding_type', 0, 'embedding_type')

class Emotion_CNN(object):

    def __init__(self,
                 batch_size=FLAGS.batch_size,
                 learning_rate=FLAGS.learning_rate,
                 keep_prob=FLAGS.keep_prob,
                 l2_reg=FLAGS.l2_reg,
                 display_step=FLAGS.display_step,
                 training_iter=FLAGS.training_iter,
                 embedding_dim=FLAGS.embedding_dim,
                 n_class=FLAGS.n_class,
                 max_doc_len=FLAGS.max_doc_len,
                 train_file_path=FLAGS.train_file_path,
                 w2v_file=FLAGS.embedding_file_path,
                 test_index=FLAGS.test_index,
                 embedding_type=FLAGS.embedding_type,
                 scope='test'
                 ):
        self.batch_size = batch_size
        self.learning_rate = learning_rate
        self.Keep_Prob = keep_prob
        self.l2_reg = l2_reg

        self.display_step = display_step
        self.training_iter = training_iter
        self.embedding_dim = embedding_dim
        self.n_class = n_class
        self.max_doc_len = max_doc_len

        self.train_file_path = train_file_path
        self.w2v_file = w2v_file
        self.test_index = test_index
        self.embedding_type = embedding_type
        self.scope=scope

        self.word_id_mapping, self.w2v = load_w2v(
            self.w2v_file, self.embedding_dim)
        if embedding_type == 0:  # Pretrained and Untrainable
            self.word_embedding = tf.constant(
                self.w2v, dtype=tf.float32, name='word_embedding')
        elif embedding_type == 1:  # Pretrained and Trainable
            self.word_embedding = tf.Variable(
                self.w2v, dtype=tf.float32, name='word_embedding')
        elif embedding_type == 2:  # Random and Trainable
            self.word_embedding = tf.Variable(tf.random_uniform(
                [len(self.word_id_mapping) + 1, self.embedding_dim], -0.1, 0.1), name='word_embedding')

        with tf.name_scope('inputs'):
            self.x = tf.placeholder(tf.int32, [None, self.max_doc_len])
            self.y = tf.placeholder(tf.float32, [None, self.n_class])
            self.doc_len = tf.placeholder(tf.int32, None)
            self.keep_prob = tf.placeholder(tf.float32)

        def init_variable(shape):
            initial = tf.random_uniform(shape, -0.01, 0.01)
            return tf.Variable(initial)

        with tf.name_scope('weights'):
            self.weights = {
                'softmax': init_variable([100, self.n_class]),
                'softmax1': init_variable([200, self.n_class]),
            }

        with tf.name_scope('biases'):
            self.biases = {
                'softmax': init_variable([self.n_class]),
            }

    def model(self, inputs):
        inputs = tf.reshape(inputs, [-1, self.max_doc_len, self.embedding_dim])
        # with tf.name_scope('doc_encode'):
        #     outputs, state = tf.nn.dynamic_rnn(
        #         cell=tf.nn.rnn_cell.GRUCell(100),
        #         inputs=inputs,
        #         sequence_length=self.doc_len,
        #         dtype=tf.float32,
        #         scope=self.scope
        #     )

        #LSTM
        # with tf.name_scope('doc_encode'):
        #     outputs, state = tf.nn.dynamic_rnn(
        #         cell=tf.nn.rnn_cell.LSTMCell(100),
        #         inputs=inputs,
        #         sequence_length=self.doc_len,
        #         dtype=tf.float32,
        #         scope=self.scope)

        #Bi - LSTM
        with tf.name_scope('doc_encode'):
            outputs, state = tf.nn.bidirectional_dynamic_rnn(
                cell_fw=tf.nn.rnn_cell.LSTMCell(100),
                cell_bw=tf.nn.rnn_cell.LSTMCell(100),
                inputs=inputs,
                sequence_length=self.doc_len,
                dtype=tf.float32,
                scope=self.scope)
            outputs = tf.concat(1, state[1])
            


        with tf.name_scope('softmax'):
            # outputs = tf.nn.dropout(state, keep_prob=self.keep_prob)
            # outputs = tf.nn.dropout(state[1], keep_prob=self.keep_prob)
            outputs = tf.nn.dropout(outputs, keep_prob=self.keep_prob)
            predict = tf.matmul(outputs, self.weights['softmax1']) + self.biases['softmax']
            # predict = tf.matmul(outputs, self.weights['softmax']) + self.biases['softmax']
            predict = tf.nn.softmax(predict)

        return predict

    def run(self):
        inputs = tf.nn.embedding_lookup(self.word_embedding, self.x)
        prob = self.model(inputs)

        with tf.name_scope('loss'):
            cost = - tf.reduce_mean(self.y * tf.log(prob))
            reg, variables = tf.nn.l2_loss(self.word_embedding), ['softmax']
            for vari in variables:
                reg += tf.nn.l2_loss(self.weights[vari]) + \
                    tf.nn.l2_loss(self.biases[vari])
            cost += reg * self.l2_reg

        with tf.name_scope('train'):
            global_step = tf.Variable(
                0, name="tr_global_step", trainable=False)
            optimizer = tf.train.AdamOptimizer(
                learning_rate=self.learning_rate).minimize(cost, global_step=global_step)

        with tf.name_scope('predict'):
            correct_pred = tf.equal(tf.argmax(prob, 1), tf.argmax(self.y, 1))
            accuracy = tf.reduce_mean(tf.cast(correct_pred, tf.float32))
            correct_num = tf.reduce_sum(tf.cast(correct_pred, tf.int32))

        with tf.name_scope('summary'):
            localtime = time.strftime("%X %Y-%m-%d", time.localtime())
            Summary_dir = 'Summary/' + localtime

            info = 'batch-{}, lr-{}, kb-{}, l2_reg-{}'.format(
                self.batch_size,  self.learning_rate, self.Keep_Prob, self.l2_reg)
            info = info + '\ntrain_file_path:' + self.train_file_path + '\ntest_index:' + str(self.test_index) + '\nembedding_type:' + str(self.embedding_type) + '\nMethod: Emotion_GRU'
            summary_acc = tf.scalar_summary('ACC ' + info, accuracy)
            summary_loss = tf.scalar_summary('LOSS ' + info, cost)
            summary_op = tf.merge_summary([summary_loss, summary_acc])

            test_acc = tf.placeholder(tf.float32)
            test_loss = tf.placeholder(tf.float32)
            summary_test_acc = tf.scalar_summary('ACC ' + info, test_acc)
            summary_test_loss = tf.scalar_summary('LOSS ' + info, test_loss)
            summary_test = tf.merge_summary(
                [summary_test_loss, summary_test_acc])

            train_summary_writer = tf.train.SummaryWriter(
                Summary_dir + '/train')
            test_summary_writer = tf.train.SummaryWriter(Summary_dir + '/test')

        with tf.name_scope('saveModel'):
            saver = tf.train.Saver(write_version=tf.train.SaverDef.V2)
            save_dir = 'Models/' + localtime + '/'
            if not os.path.exists(save_dir):
                os.makedirs(save_dir)

        with tf.name_scope('readData'):
            print '----------{}----------'.format(time.strftime("%Y-%m-%d %X", time.localtime()))
            tr_x, tr_y, tr_doc_len, te_x, te_y, te_doc_len, ev_x, ev_y, ev_doc_len= load_data_for_Emotion_CNN(
                self.train_file_path,
                self.word_id_mapping,
                self.max_doc_len,
                self.test_index,
                self.n_class
            )
            print 'train docs: {}    test docs: {}'.format(len(tr_y), len(te_y))
            print 'training_iter:', self.training_iter
            print info
            print '----------{}----------'.format(time.strftime("%Y-%m-%d %X", time.localtime()))

        config = tf.ConfigProto()
        config.gpu_options.allow_growth = True

        with tf.Session() as sess:
            sess.run(tf.initialize_all_variables())
            max_acc, bestIter = 0., 0

            def test():
                acc, loss, cnt = 0., 0., 0
                for test, num in self.get_batch_data(te_x, te_y, te_doc_len, 20, keep_prob=1.0):
                    _loss, _acc = sess.run([cost, correct_num], feed_dict=test)
                    acc += _acc
                    loss += _loss * num
                    cnt += num
                loss = loss / cnt
                acc = acc / cnt
                return loss, acc

            def new_test():
                feed_dict = {
                    self.x: ev_x,
                    self.doc_len: ev_doc_len,
                    self.keep_prob: 1.0,
                }
                y_true = ev_y
                y_pred_p = sess.run(prob, feed_dict=feed_dict)
                y_pred = np.ceil(y_pred_p-0.15)
                # y_pred  = calibrated_label_ranking(y_pred_p)
                Emotion_eval(y_true, y_pred, y_pred_p)

            if self.training_iter==0:
                saver.restore(sess, 'Models/10:01:44 2017-03-11/-856')
                loss, acc=test()
                print loss,acc
                new_test()

            for i in xrange(self.training_iter):

                for train, _ in self.get_batch_data(tr_x, tr_y, tr_doc_len, self.batch_size, self.Keep_Prob):
                    _, step, summary, loss, acc = sess.run(
                        [optimizer, global_step, summary_op, cost, accuracy], feed_dict=train)
                    train_summary_writer.add_summary(summary, step)
                    print 'Iter {}: mini-batch loss={:.6f}, acc={:.6f}'.format(step, loss, acc)

                if i % self.display_step == 0:
                    loss, acc=test()

                    if acc > max_acc:
                        max_acc = acc
                        bestIter = step
                        saver.save(sess, save_dir, global_step=step)
                        new_test()

                    summary = sess.run(summary_test, feed_dict={
                                       test_loss: loss, test_acc: acc})
                    test_summary_writer.add_summary(summary, step)
                    print '----------{}----------'.format(time.strftime("%Y-%m-%d %X", time.localtime()))
                    print 'Iter {}: test loss={:.6f}, test acc={:.6f}'.format(step, loss, acc)
                    print 'round {}: max_acc={} BestIter={}\n'.format(i, max_acc, bestIter)

            print 'Optimization Finished!'

    def get_batch_data(self, x, y, doc_len, batch_size, keep_prob):
        for index in batch_index(len(y), batch_size, 1):
            feed_dict = {
                self.x: x[index],
                self.y: y[index],
                self.doc_len: doc_len[index],
                self.keep_prob: keep_prob,
            }
            yield feed_dict, len(index)



def main(_):
    
    for i in range(3):
        for j in [1,3,5]:
            print('hhhe_ebdt{}_index{}.txt'.format(i, j))
            # sys.stdout = open('Bi_LSTM_ebdt'+str(i)+'_index'+str(j)+'.txt', 'w')
            obj = Emotion_CNN(
               test_index=j,
               embedding_type=i,
               scope='hhhe_ebdt{}_index{}.txt'.format(i, j)
            )
            obj.run()
    
    
if __name__ == '__main__':
    tf.app.run()
